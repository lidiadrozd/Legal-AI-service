"""All 38 full forms: factual composition, roles, actual API files, failures."""
from copy import deepcopy
from io import BytesIO
from unittest.mock import AsyncMock
from decimal import Decimal
import json
import pytest
from docx import Document
from complete_form_cases import make_state
from app.services.document_form_rules import PROFILE_BY_FORM
from app.services.document_form_composition import prepare_form_document,form_presentation_fields
from app.services.document_scenarios import SCENARIOS
from app.services.document_template_library import render_package_blocks,format_template_fields
from app.services.document_export_contract import validate_export_blocks
from app.services.document_docx_template import fill_docx_template
from app.services.document_workflow import advance_interview
from app.services.llm_cost import TokenUsage
from types import SimpleNamespace

KEYS=list(PROFILE_BY_FORM)


def test_spelled_amount_is_restored_only_when_equal_to_original_literal():
    from app.services.document_editorial_grammar import restore_spelled_source_numbers
    assert restore_spelled_source_numbers('долг 100000 рублей','Не возвратил сто тысяч рублей.')=='Не возвратил 100000 рублей.'
    assert restore_spelled_source_numbers('долг 100000 рублей','Не возвратил девяносто тысяч рублей.')=='Не возвратил девяносто тысяч рублей.'
    assert restore_spelled_source_numbers('получено 01.10.2026','Ответ одного родителя.')=='Ответ одного родителя.'


def test_broken_json_fragment_cannot_be_treated_as_official_prose():
    from app.services.document_form_composition import _validate_slot
    assert not _validate_slot('facts','{\\n','ну деньги не вернул','sentence')


@pytest.mark.asyncio
@pytest.mark.parametrize('key',KEYS)
async def test_complete_factual_form_has_law_body_signer_and_no_editor_markers(key):
    source=make_state(key);original=deepcopy(source['fields'])
    state,usage=await prepare_form_document(source,None)
    assert state['form_review_fields']==[],(key,state['form_review_fields'])
    assert source['fields']==original
    scenario=SCENARIOS[key];fields=form_presentation_fields(state);package=state['text_package']
    blocks=render_package_blocks(package,scenario,fields,format_template_fields(scenario,fields))
    validate_export_blocks(blocks)
    doc=Document(BytesIO(fill_docx_template(package,scenario,fields)))
    text='\n'.join(p.text for p in doc.paragraphs)+'\n'+'\n'.join(c.text for t in doc.tables for r in t.rows for c in r.cells)
    assert 'Тестова Анна Ивановна' in text
    # Court documents and complaints must show their legal basis.  A private
    # contract is not made safer by adding a generic citation to its text:
    # its enforceable terms are the parties' own agreed clauses.
    if scenario.family not in {'contract', 'act', 'authority'}:
        assert 'стат' in text.lower() and ('ГК РФ' in text or 'СК РФ' in text or 'ТК РФ' in text or 'ГПК РФ' in text or '229-ФЗ' in text or '2300-1' in text)
    for marker in ('{{','Source_text','&DNR','требуется редакция','Я добавила необходимые','Какой полный адрес'):
        assert marker not in text,(key,marker)
    if key in {'claim_labor_salary','pretense_labor_settlement','claim_labor_reinstatement','labor_resignation'}:
        assert 'Наймодатель' not in text and 'договор аренды' not in text
    if key in {'claim_debt_loan','claim_debt_services','claim_rent_deposit','claim_damage_property','claim_damage_flood','claim_labor_salary'}:
        requests='\n'.join(b['text'] for b in blocks if b['role']=='request')
        assert '100 000 рублей' in requests


@pytest.mark.asyncio
@pytest.mark.parametrize('key',KEYS)
async def test_each_complete_form_downloads_with_real_facts_when_provider_offline(key,client,db_session,tmp_path,monkeypatch):
    from app.models.chat import ChatSession
    from app.models.document import Document as StoredDocument
    state=make_state(key)
    monkeypatch.setattr('app.core.config.settings.DOCUMENTS_STORAGE_DIR',str(tmp_path))
    provider=AsyncMock(side_effect=RuntimeError('synthetic provider outage'))
    monkeypatch.setattr('app.services.gigachat_client.get_gigachat_client',provider)
    chat=ChatSession(user_id=1,title=key,document_workflow=state)
    db_session.add(chat);await db_session.commit()
    response=await client.post(f'/documents/interviews/{chat.id}/export')
    assert response.status_code==201,(key,response.text)
    identity=response.json()['document_id']
    download=await client.get('/documents/'+identity+'/download')
    assert download.status_code==200 and download.content.startswith(b'PK')
    assert Document(BytesIO(download.content)).paragraphs
    stored=await db_session.get(StoredDocument,identity)
    assert stored.generation_meta['scenario']==key
    for field,item in state['fields'].items():
        if item.get('original') is not None:
            assert stored.generation_meta['fields'][field]['value']==item['value'],(key,field)


@pytest.mark.asyncio
async def test_unverified_colloquial_text_is_a_named_gap_and_file_still_downloads(client,db_session,tmp_path,monkeypatch):
    from app.models.chat import ChatSession
    from app.models.document import Document as StoredDocument
    state=make_state('pretense_debt_loan');raw='ну знакомый так и не вернул мне 100000 рублей'
    state['fields']['facts']={'status':'filled','value':raw,'original':raw,'evidence':raw}
    monkeypatch.setattr('app.core.config.settings.DOCUMENTS_STORAGE_DIR',str(tmp_path))
    monkeypatch.setattr('app.services.gigachat_client.get_gigachat_client',AsyncMock(side_effect=RuntimeError('offline')))
    chat=ChatSession(user_id=1,title='source safe',document_workflow=state)
    db_session.add(chat);await db_session.commit()
    response=await client.post(f'/documents/interviews/{chat.id}/export')
    assert response.status_code==201,response.text
    downloaded=await client.get('/documents/'+response.json()['document_id']+'/download')
    text='\n'.join(p.text for p in Document(BytesIO(downloaded.content)).paragraphs)
    assert raw not in text and 'требуется редакция' not in text
    assert '['+next(f.label.lower() for f in SCENARIOS[state['scenario']].fields if f.key=='facts')+']' in text
    stored=await db_session.get(StoredDocument,response.json()['document_id'])
    assert stored.generation_meta['fields']['facts']['value']==raw
    assert any(i['field']=='facts' for i in stored.generation_meta['readiness']['legal_review'])


@pytest.mark.asyncio
async def test_batch_editor_cannot_change_an_amount_even_if_its_reviewer_would_agree():
    state=make_state('pretense_debt_loan');raw='ну знакомый не вернул мне 100000 рублей'
    state['fields']['facts']={'status':'filled','value':raw,'original':raw}
    # Other prose now also reaches the provider. Approve those fields while
    # trying to slip a changed amount through the editor and reviewer.
    fact_attempts=[]
    async def complete(messages, **kwargs):
        data=json.loads(messages[1]['content'])
        if 'slots' in data:
            text=json.dumps({k:{'meaning_preserved':True,'business_style':True,'fits_context':True,'reason':'approved'} for k in data['slots']})
        else:
            text=data['source_text']
            if text==raw:
                fact_attempts.append(text)
                text='Заёмщик не возвратил денежные средства в размере 90000 рублей.'
        return SimpleNamespace(content=text,usage=TokenUsage(1,1,2,False))
    provider=SimpleNamespace(chat_completion=AsyncMock(side_effect=complete))
    result,_=await prepare_form_document(state,provider)
    assert result['form_review_fields']==['facts'] and 'facts' not in result['draft_fields']
    assert result['fields']['facts']['value']==raw
    assert len(fact_attempts)==2  # Both edits rejected before semantic review.


@pytest.mark.asyncio
async def test_labelled_answers_fill_several_fields_without_polluting_current_question(monkeypatch):
    state=make_state('contract_services')
    for key in ('amount','term','payment'):state['fields'].pop(key,None)
    state.update(phase='collecting',last_questions=['term'])
    unavailable=AsyncMock(side_effect=RuntimeError('Supplemental extraction unavailable'))
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client',unavailable)
    result,answer,_=await advance_interview(state,'Цена: 50000 рублей; Порядок расчётов: перевод после приёмки')
    assert Decimal(result['fields']['amount']['value'])==50000
    assert 'payment' in result['fields'] and result['fields']['payment']['status']=='filled'
    assert result['last_questions']==['term']
    assert result['fields'].get('term',{}).get('status')!='filled'
    # Field/output assertions above verify the deterministic fallback.
