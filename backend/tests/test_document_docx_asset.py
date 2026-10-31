"""Real-template export: layout preservation, branch fidelity and download path."""
from copy import deepcopy
from io import BytesIO
import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zipfile import ZipFile
import pytest
from docx import Document
from docx.oxml.ns import qn
from app.services.document_scenarios import SCENARIOS
from app.services.document_template_library import load_text_package
from app.services.document_docx_template import fill_docx_template, load_docx_asset
from app.services.document_drafting import facts_digest
from app.services.document_export_contract import EDITOR_VERSION
from app.services.document_workflow import new_state
from app.services.llm_cost import TokenUsage
from app.services.document_editorial_grammar import normalize_room_counts,repair_editorial_surface


def fixture_fields(deposit='нет'):
    scenario=SCENARIOS['contract_housing']
    fields={f.key:{'status':'unknown','value':None} for f in scenario.fields}
    for key,value in dict(sender='Тестова Анна Ивановна',recipient='Примеров Илья Сергеевич',
        property='г. Екатеринбург, ул. Мира, д. 33, кв. 67',place='Екатеринбург',date='2026-10-27',
        start_date='2026-11-01',term='2 года',amount='45000.00',deposit=deposit,
        signature='Тестова Анна Ивановна',counterparty_signature='Примеров Илья Сергеевич',
        ownership='Право собственности подтверждено выпиской ЕГРН.',residents='Отсутствуют.',
        sender_details='• Серия и номер: 45 12 345678 (где первые 4 цифры — серия, остальные 6 — номер) • Дата выдачи: 15.05.2018',
        recipient_details='Серия и номер: 45 12 885678 ( • Дата выдачи: 15.05.2014',
        attachments='Отсутствуют.',liability='Стороны отвечают за причинённый ими ущерб.',
        deposit_amount='50000.00',deposit_terms='Платёж возвращается при отсутствии ущерба.').items():
        fields[key]={'status':'filled','value':value}
    fields['additional_terms']={'status':'not_applicable','value':None}
    return fields


def texts(doc): return '\n'.join(doc.element.itertext())


@pytest.mark.parametrize('deposit',['да','нет'])
def test_actual_docx_asset_preserves_layout_and_conditions(deposit):
    scenario=SCENARIOS['contract_housing'];package=load_text_package(scenario)
    original,_=load_docx_asset(package,scenario)
    template=Document(BytesIO(original));result=Document(BytesIO(fill_docx_template(package,scenario,fixture_fields(deposit))))
    assert len(result.tables)==len(template.tables)==1
    assert len(result.tables[0].columns)==2
    assert result.sections[0].page_width == template.sections[0].page_width
    assert result.sections[0].page_height == template.sections[0].page_height
    assert result.sections[0].top_margin == template.sections[0].top_margin
    assert result.sections[0].bottom_margin == template.sections[0].bottom_margin
    assert result.sections[0].left_margin == template.sections[0].left_margin
    assert result.sections[0].right_margin == template.sections[0].right_margin
    assert result.sections[0].different_first_page_header_footer
    assert result.sections[0].header_distance.cm == pytest.approx(1, abs=.01)
    assert 'PAGE' in result.sections[0].header.part.blob.decode('utf-8')
    assert 'PAGE' not in result.sections[0].footer.part.blob.decode('utf-8')
    with ZipFile(BytesIO(original)) as a,ZipFile(BytesIO(fill_docx_template(package,scenario,fixture_fields(deposit)))) as b:
        assert a.read('word/styles.xml')==b.read('word/styles.xml') or Document(BytesIO(original)).styles.element.xml==result.styles.element.xml
    value=texts(result)
    assert '{{' not in value and 'ДАННЫЕ_' not in value
    assert 'Тестова Анна Ивановна' in value and '2.1. Дата начала найма: 01.11.2026' in value
    assert '1.1.' in value and '6.2.' in value
    assert '..' not in value and 'где первые' not in value and '( •' not in value
    assert ('3.5. Условия' in value)==(deposit=='да')
    assert ('Обеспечительный платёж не предусмотрен.' in value)==(deposit=='нет')
    assert not result.element.xpath('//w:sdt')


def test_multiline_values_are_text_not_xml_or_template_commands():
    fields=fixture_fields();fields['liability']['value']='Первая строка.\nВторая строка <w:p/> & условия.'
    doc=Document(BytesIO(fill_docx_template(load_text_package(SCENARIOS['contract_housing']),SCENARIOS['contract_housing'],fields)))
    assert 'Вторая строка <w:p/> & условия.' in texts(doc)
    p=next(p for p in doc.paragraphs if 'Первая строка.' in p.text)
    assert len(p._p.findall('.//'+qn('w:br')))==0
    assert p.text.startswith('5.1.')
    assert any(p.text.startswith('5.2. Вторая строка') for p in doc.paragraphs)


def test_missing_required_value_remains_a_label_not_example_data():
    fields=fixture_fields();fields['property']={'status':'unknown','value':None};fields['deposit']={'status':'unknown','value':None}
    doc=Document(BytesIO(fill_docx_template(load_text_package(SCENARIOS['contract_housing']),SCENARIOS['contract_housing'],fields)))
    assert '[адрес передаваемого жилья]' in texts(doc) and '[наличие обеспечительного платежа]' in texts(doc)
    assert 'Уфа' not in texts(doc)


def test_asset_hash_and_traversal_are_checked_before_export():
    scenario=SCENARIOS['contract_housing'];package=load_text_package(scenario)
    for changes in ({'template_sha256':'0'*64},{'template':'../outside.docx'}):
        modified=deepcopy(package);modified['docx_asset'].update(changes)
        with pytest.raises(ValueError): fill_docx_template(modified,scenario,fixture_fields())


def test_all_asset_exports_move_page_number_to_the_standard_header():
    for scenario in SCENARIOS.values():
        package = load_text_package(scenario)
        if not package.get('docx_asset'):
            continue
        fields = {field.key: {'status': 'unknown', 'value': None} for field in scenario.fields}
        document = Document(BytesIO(fill_docx_template(package, scenario, fields)))
        for section in document.sections:
            assert section.different_first_page_header_footer
            assert section.header_distance.cm == pytest.approx(1, abs=.01)
            assert 'PAGE' in section.header.part.blob.decode('utf-8')
            assert 'PAGE' not in section.footer.part.blob.decode('utf-8')


@pytest.mark.parametrize('number,word',[(1,'комната'),(2,'комнаты'),(3,'комнаты'),(4,'комнаты'),
    (5,'комнат'),(11,'комнат'),(12,'комнат'),(13,'комнат'),(21,'комната'),(23,'комнаты')])
def test_room_count_agreement_in_a_property_list(number,word):
    assert normalize_room_counts(f'Квартира, {number} комнат, 50 квадратных метров.')==f'Квартира, {number} {word}, 50 квадратных метров.'
    assert normalize_room_counts('Квартира состоит из 3 комнат.')=='Квартира состоит из 3 комнат.'


def test_monthly_payment_repair_requires_the_same_source_phrase():
    edited='Не более 10 % от суммы меся.'
    assert repair_editorial_surface('liability','Не более 10% от суммы месячной платы.',edited)=='Не более 10 % от суммы месячной платы.'
    assert repair_editorial_surface('liability','Не более 10% от общей суммы.',edited)==edited


def test_party_titles_are_bold_unnumbered_and_only_conditions_consume_numbers():
    fields=fixture_fields();fields['liability']['value']=(
        '2. Ответственность Нанимателя:\n• За просрочку: пеня 0,1 %.\n• За ущерб: возмещение.\n'
        '3. Ответственность Наймодателя:\n• За задержку: пеня 0,1 %.')
    doc=Document(BytesIO(fill_docx_template(load_text_package(SCENARIOS['contract_housing']),SCENARIOS['contract_housing'],fields)))
    for title in ['Ответственность Нанимателя:','Ответственность Наймодателя:']:
        p=next(p for p in doc.paragraphs if p.text==title)
        assert p.paragraph_format.keep_with_next and any(r.bold for r in p.runs)
    clauses=[p.text for p in doc.paragraphs if re.match(r'^5\.\d+\.',p.text)]
    assert len(clauses)==3
    assert clauses[0].startswith('5.1. За просрочку') and clauses[-1].startswith('5.3. За задержку')


def test_docx_controls_do_not_duplicate_template_punctuation_or_break_numbered_lists():
    from lxml import etree
    from app.services.document_docx_template import NS, W, _write_inline, _write_paragraphs

    inline=etree.fromstring(f'''<w:p xmlns:w="{W}">
      <w:sdt><w:sdtContent><w:r><w:t>placeholder</w:t></w:r></w:sdtContent></w:sdt>
      <w:r><w:t>, далее</w:t></w:r>
    </w:p>''')
    control=inline.xpath('./w:sdt',namespaces=NS)[0]
    _write_inline(control,'Паспорт выдан 18.06.2020.')
    inline_text=re.sub(r'\s+',' ',''.join(inline.itertext())).strip()
    inline_text=re.sub(r'\s+([,.;:!?])',r'\1',inline_text)
    assert '18.06.2020.,' not in inline_text
    assert '18.06.2020, далее' in inline_text

    listing=etree.fromstring(f'''<w:body xmlns:w="{W}">
      <w:p><w:r><w:t>Приложения: </w:t></w:r>
        <w:sdt><w:sdtContent><w:r><w:t>placeholder</w:t></w:r></w:sdtContent></w:sdt>
        <w:r><w:t>.</w:t></w:r>
      </w:p>
    </w:body>''')
    control=listing.xpath('.//w:sdt',namespaces=NS)[0]
    _write_paragraphs(control,'1. Выписка ЕГРН.\n2. Передаточный акт.',{'preserve_list_numbers':True})
    rendered=''.join(listing.itertext())
    assert 'Приложения: 1. Выписка ЕГРН.' in rendered
    assert 'Приложения: .1.' not in rendered
    assert rendered.count('Приложения:') == 1
    assert '2. Передаточный акт.' in rendered


@pytest.mark.asyncio
async def test_api_uses_maintained_docx_and_converts_that_same_docx_for_pdf(db_session,test_user,monkeypatch,tmp_path,client):
    from app.models.chat import ChatSession
    from app.models.document import Document as StoredDocument
    from app.api.documents import prepare_interview_file
    import app.api.documents as api
    monkeypatch.setattr(api,'_storage_root',lambda:tmp_path)
    monkeypatch.setattr('app.services.document_quality.quality_issues',lambda state:[])
    fields=fixture_fields()
    state=new_state('Нужен договор найма квартиры');state.update(scenario='contract_housing',schema_version=2,phase='ready',fields=fields,
        text_package=load_text_package(SCENARIOS['contract_housing']),draft_fields={},draft_version=EDITOR_VERSION,draft_digest=facts_digest(fields))
    # Fields not provided in this fixture are explicitly unknown, as permitted
    # for a draft. No provider is needed for this layout/download test.
    monkeypatch.setattr('app.services.document_drafting.narrative_keys',lambda state:[])
    chat=ChatSession(user_id=test_user.id,title='Template QA',document_workflow=state)
    db_session.add(chat);await db_session.flush()
    result=await prepare_interview_file(chat,test_user.id,db_session)
    stored=await db_session.get(StoredDocument,result.document_id)
    docx=Path(stored.file_path).read_bytes()
    assert len(Document(BytesIO(docx)).tables)==1
    response=await client.get('/documents/'+result.document_id+'/download')
    assert response.status_code==200 and response.content==docx
    assert stored.generation_meta['docx_asset']['template']==state['text_package']['docx_asset']['template']
    calls=[]
    def convert(payload):
        calls.append(payload);assert len(Document(BytesIO(payload)).tables)==1
        return b'%PDF-1.4 test converter'
    monkeypatch.setattr('app.services.document_docx_template.docx_to_pdf',convert)
    chat.document_workflow={**chat.document_workflow,'output_format':'pdf'}
    result=await prepare_interview_file(chat,test_user.id,db_session)
    stored=await db_session.get(StoredDocument,result.document_id)
    assert calls==[docx] and Path(stored.file_path).read_bytes().startswith(b'%PDF-')
