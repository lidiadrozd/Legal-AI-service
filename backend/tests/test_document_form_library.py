"""Reported family confusion and the boundary between samples and user facts."""
from copy import deepcopy
from io import BytesIO
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from docx import Document

from app.services.document_dialogue import document_kind, infer_scenario, scenario_candidates, leaves_blank
from app.services.document_workflow import new_state, advance_interview, sanitize_interview, pending_fields, normalize_field
from app.services.document_scenarios import SCENARIOS
from app.services.document_source_rag import select_document_template, retrieve_source_sections, search_form_sources, source_forms, sanitize_reference
from app.services.document_template_library import render_package_blocks, format_template_fields
from app.services.document_drafting import canonical_editorial
from app.services.document_drafting import prepare_document_draft, validate_edit, DraftPreparationError
from app.services.llm_cost import TokenUsage
from app.services.document_export_contract import formal_text
from app.services.document_workflow_docx import build_legal_docx


@pytest.mark.parametrize('prompt,kind,scenario', [
    ('хочу сдавать свою вторую квартиру, нужен договор', 'contract', 'contract_housing'),
    ('Нужен договор найма квартиры на 2 года', 'contract', 'contract_housing'),
    ('Составь договор на ремонт квартиры', 'contract', 'contract_work'),
    ('Подготовь договор оказания услуг', 'contract', 'contract_services'),
    ('Составь договор займа', 'contract', 'contract_loan'),
    ('Нужна претензия по задолженности по договору аренды', 'pretense', 'pretense_debt_rent'),
    ('Нужен иск о взыскании денег по договору займа', 'claim', 'claim_debt_loan'),
    ('Нужна жалоба в Роспотребнадзор на магазин', 'complaint', 'complaint_consumer_agency'),
    ('Нужна расписка о получении займа', 'receipt', 'act_loan_receipt'),
    ('Подготовь акт выполненных работ', 'act', 'act_work'),
    ('Нужна доверенность на бабушку', 'authority', 'power_of_attorney'),
])
def test_document_kind_is_a_hard_retrieval_filter(prompt, kind, scenario):
    state = new_state(prompt)
    assert document_kind(state) == kind
    assert infer_scenario(state, '') == scenario
    assert scenario in scenario_candidates(state)
    if kind == 'contract': assert all(key.startswith('contract_') for key in scenario_candidates(state))


@pytest.mark.asyncio
async def test_exact_housing_request_starts_from_housing_form_without_network(monkeypatch):
    offline = AsyncMock(side_effect=AssertionError('Exact type needs no AI classifier'))
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client', offline)
    prompt = 'хочу сдавать свою вторую квартиру, нужен договор'
    state, answer, _ = await advance_interview(new_state(prompt), prompt)
    assert state['scenario'] == 'contract_housing' and state['last_questions'] == ['sender']
    assert 'Наймодатель' in answer and 'заявител' not in answer.lower()
    assert state['template_selection']['scenario'] == 'contract_housing'
    assert state['template_selection']['source_forms']
    assert not offline.called


def test_legacy_rent_pretense_cannot_keep_its_dispute_answers_in_new_contract():
    state = new_state('хочу сдавать свою вторую квартиру, нужен договор')
    state.update(scenario='pretense_debt_rent', phase='ready', last_questions=[])
    state['fields'] = {key: {'status':'filled','value':value} for key,value in {
        'sender':'Иванова Ирина Фёдоровна', 'amount':'45000.00', 'facts':'ничего не произошло',
        'due_date':'2026-11-01', 'requests':'соблюдать порядок в доме', 'response_term':'2 года',
    }.items()}
    repaired = sanitize_interview(state)
    assert repaired['scenario'] == 'contract_housing'
    assert repaired['fields']['sender']['value'] == 'Иванова Ирина Фёдоровна'
    assert not {'amount','facts','requests','due_date','response_term'} & repaired['fields'].keys()
    assert repaired['previous_fields'] == state['fields'] and repaired['phase'] == 'collecting'


@pytest.mark.asyncio
async def test_duration_is_not_a_date_and_unknown_address_can_be_spelled_with_a_space():
    state = new_state('Нужен договор найма квартиры')
    state.update(scenario='contract_housing', phase='collecting', schema_version=2, last_questions=['term'])
    state, _, _ = await advance_interview(state, 'на 2 года')
    assert state['fields']['term']['value'] == '2 года'
    assert state['fields']['term']['status'] == 'filled'
    assert leaves_blank('не известен')
    state['last_questions'] = ['recipient_address']
    state, _, _ = await advance_interview(state, 'не известен')
    assert state['fields']['recipient_address']['status'] == 'unknown'
    spec = next(f for f in SCENARIOS['contract_housing'].fields if f.key=='sender_address')
    value,error = normalize_field(spec,'Екатеринбург Мира 33 67')
    assert error is None and value == 'г. Екатеринбург, ул. Мира, д. 33, кв. 67'


@pytest.mark.asyncio
async def test_missing_contract_subtype_does_not_ask_model_to_choose_a_pretense(monkeypatch):
    offline = AsyncMock(side_effect=AssertionError('Must clarify the missing contract type locally'))
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client', offline)
    prompt='Нужен договор дарения квартиры'
    state, answer, _ = await advance_interview(new_state(prompt), prompt)
    assert state['scenario'] is None and state['phase']=='classifying'
    assert 'договор' in answer.lower() and not offline.called


def test_original_forms_are_hashed_and_different_families_never_mix():
    assert len(source_forms()) >= 30
    contracts=search_form_sources('квартиры',document_kind='contract',limit=100)
    assert contracts and all(row['document_kind']=='contract' for row in contracts)
    result=retrieve_source_sections('contract_housing','задолженность по заработной плате')
    assert all(source['id'].startswith('contract-') for source in result['sources'])
    package,selection=select_document_template(SCENARIOS['contract_housing'],'сдать квартиру')
    assert package['scenario']=='contract_housing' and len(package['blocks'])>20
    assert selection['source_forms'] and selection['coverage']=='structured'
    assert 'Иванов Иван Иванович' not in json.dumps(result,ensure_ascii=False)
    assert '8000' not in sanitize_reference('Паспорт 8000 000000. Иванов Иван Иванович.')


def test_attachment_grammar_does_not_split_party_names_or_duplicate_requests():
    rendered=canonical_editorial('attachments','Чек, фотографии упаковки и письменного обращения','complaint_consumer_agency')
    assert rendered=='Чек.\nФотографии упаковки.\nПисьменное обращение.'
    text=canonical_editorial('attachments','Договор между Ивановым и Петровым','contract_housing')
    assert text.count('\n')==0
    assert not formal_text('Заявитель приобрела товар.')
    assert not formal_text('Просить рассмотреть нарушение.')
    scenario=SCENARIOS['complaint_consumer_agency']
    package,_=select_document_template(scenario,'просроченный йогурт')
    fields={f.key:{'status':'unknown','value':None} for f in scenario.fields}
    fields['requests']={'status':'filled','value':'Прошу рассмотреть обстоятельства и принять меры в пределах компетенции органа.'}
    blocks=render_package_blocks(package,scenario,fields,format_template_fields(scenario,fields))
    doc=Document(BytesIO(build_legal_docx(scenario.title,blocks)))
    text='\n'.join(p.text for p in doc.paragraphs)
    assert text.count('Прошу рассмотреть')==1 and 'Ответ на обращение' in text
    assert 'продавца или исполнителя' in text.lower() and '[адрес продавца]' not in text
    assert not validate_edit('При прекращении договора жильё возвращается наймодателю.',
        'В день прекращения договора жильё возвращается наймодателю.')


@pytest.mark.asyncio
async def test_source_catalog_api_returns_metadata_without_raw_template_examples(client):
    response=await client.get('/documents/form-sources',params={'q':'квартиры','document_kind':'contract','limit':100})
    assert response.status_code==200 and response.json()
    assert all(row['document_kind']=='contract' and 'text' not in row for row in response.json())


@pytest.mark.asyncio
@pytest.mark.parametrize('approved', [True, False])
async def test_model_cannot_block_valid_source_or_publish_unreviewed_source(approved):
    source='Я приобрела йогурт в магазине.'
    assert not validate_edit('Заявитель приобрёл йогурт в магазине.', source)
    state=new_state('Нужна жалоба в Роспотребнадзор')
    state.update(scenario='complaint_consumer_agency',fields={'purchase':{'status':'filled','value':source}})
    usage=TokenUsage(1,1,2,False)
    client=SimpleNamespace(chat_completion=AsyncMock(side_effect=[
        SimpleNamespace(content='Заявитель приобрела йогурт в магазине.',usage=usage),
        SimpleNamespace(content='Заявитель приобрёл йогурт в магазине.',usage=usage),
        SimpleNamespace(content=json.dumps({'supported':{'purchase':approved}}),usage=usage),
    ]))
    if approved:
        result,_=await prepare_document_draft(state,client)
        assert result['draft_fields']['purchase']==source
    else:
        with pytest.raises(DraftPreparationError): await prepare_document_draft(state,client)


def test_source_integrity_rejects_changed_file_and_path_escape(tmp_path,monkeypatch):
    import hashlib
    import app.services.document_source_rag as module
    raw=tmp_path/'original.pdf'; raw.write_bytes(b'original')
    extracted=tmp_path/'text.txt'; extracted.write_bytes(('Sample form content. '*20).encode())
    item={'raw_path':raw.name,'text_path':extracted.name,
          'sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),
          'text_sha256':hashlib.sha256(extracted.read_bytes()).hexdigest()}
    (tmp_path/'manifest.json').write_text(json.dumps([item]),encoding='utf-8')
    monkeypatch.setattr(module,'SOURCE_ROOT',tmp_path)
    try:
        module.source_forms.cache_clear()
        assert len(module.source_forms())==1
        raw.write_bytes(b'tampered')
        module.source_forms.cache_clear()
        assert not module.source_forms()
        item['raw_path']='../outside.pdf'
        (tmp_path/'manifest.json').write_text(json.dumps([item]),encoding='utf-8')
        module.source_forms.cache_clear()
        assert not module.source_forms()
    finally:
        module.source_forms.cache_clear()


@pytest.mark.asyncio
async def test_prefixed_date_stays_in_the_housing_intake_without_ai(monkeypatch):
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client',AsyncMock(side_effect=AssertionError('No AI for dates')))
    state=new_state('Я сдаю квартиру, нужен договор аренды')
    state.update(scenario='contract_housing',schema_version=2,phase='collecting',last_questions=['start_date'])
    state,_,_=await advance_interview(state,'с 1.11.26')
    assert state['fields']['start_date']['value']=='2026-11-01'
    assert state['fields']['start_date']['status']=='filled'


@pytest.mark.asyncio
async def test_alimony_clarification_never_uses_services_claim_or_network(monkeypatch):
    offline=AsyncMock(side_effect=AssertionError('No classifier for a known missing form'))
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client',offline)
    prompt='иск о взыскании алиментов на ребёнка'
    state,reply,_=await advance_interview(new_state(prompt),prompt)
    assert state['scenario'] is None and 'долях к доходу' in reply
    state,reply,_=await advance_interview(state,'Бывший муж не выплатил алименты за 6 месяцев')
    assert state['scenario'] is None and state['last_questions']==[]
    assert not offline.called
    state.update(scenario='claim_debt_services',phase='collecting',fields={'sender':{'status':'filled','value':'Иванова Анна Ивановна'}})
    repaired=sanitize_interview(state)
    assert repaired['scenario'] is None and repaired['previous_fields']==state['fields']


@pytest.mark.asyncio
async def test_classifiers_nearest_template_requires_positive_subject_evidence(monkeypatch):
    from app.services.llm_cost import TokenUsage
    wrong=SimpleNamespace(chat_completion=AsyncMock(return_value=SimpleNamespace(
        content='{"scenario":"claim_debt_services","question":"Укажите ФИО"}',usage=TokenUsage(1,1,2,False))))
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client',AsyncMock(return_value=wrong))
    prompt='Нужен иск о признании права на наследство после смерти родственника'
    state,reply,_=await advance_interview(new_state(prompt),prompt)
    assert state['scenario'] is None and 'пока не удалось выбрать форму' in reply


@pytest.mark.asyncio
async def test_lowercase_exact_source_can_be_independently_reviewed_after_editor_failure():
    from app.services.llm_cost import TokenUsage
    source='вносится перед заездом, возвращается при отсутствии повреждений; из 50000 удерживается часть при ущербе свыше 1000 рублей'
    state=new_state('Нужен договор найма квартиры')
    state.update(scenario='contract_housing',fields={'deposit':{'status':'filled','value':'да'},
        'deposit_terms':{'status':'filled','value':source}})
    usage=TokenUsage(1,1,2,False)
    editor=SimpleNamespace(chat_completion=AsyncMock(side_effect=[
        SimpleNamespace(content='Удерживается сумма свыше 100 рублей.',usage=usage),
        SimpleNamespace(content='Удерживается сумма свыше 100 рублей.',usage=usage),
        SimpleNamespace(content='{"supported":{"deposit_terms":true}}',usage=usage),
    ]))
    state,_=await prepare_document_draft(state,editor)
    assert state['draft_fields']['deposit_terms']==source[:1].upper()+source[1:]
    assert '50000' in state['draft_fields']['deposit_terms'] and '1000' in state['draft_fields']['deposit_terms']
