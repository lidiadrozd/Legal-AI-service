from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
import json
import pytest
from appeal_intake_case import PROMPT,NARRATIVE
from app.services.document_workflow import new_state,advance_interview,_capture_contextual_facts,apply_updates,FieldUpdate
from app.services.document_scenarios import SCENARIOS
from app.services.document_template_library import load_text_package
from app.services.document_appeal_facts import collect_appeal_facts
from app.services.document_source_quotes import literal_evidence
from app.services.document_export_contract import role_evidence_allowed
from app.services.llm_cost import TokenUsage


def state():
    value=new_state(PROMPT)
    value.update(scenario='appeal_civil',phase='collecting',last_questions=['sender'],
        text_package=load_text_package(SCENARIOS['appeal_civil']))
    return value


def assert_facts(value):
    f=value['fields']
    assert 'Елена Викторовна Крылова' in f['sender']['value'] and 'ответчик' in f['sender']['value']
    assert 'Сергей Павлович Белов' in f['recipient']['value'] and 'истец' in f['recipient']['value']
    assert 'Лесная' in f['sender_address']['value'] and 'Центральная' not in f['sender_address']['value']
    assert 'Центральная' in f['recipient_address']['value'] and 'Контакт' not in f['recipient_address']['value']
    assert f['court']['value']=='Свердловский областной суд'
    assert f['first_court']['value']=='Кировский районный суд города Екатеринбурга'
    assert f['case_number']['value']=='2-1234/2026'
    assert f['act_date']['value']=='2026-10-23'
    assert '27 октября' in f['appeal_term']['value']
    assert 'Копию решения' in f['appeal_term']['value']
    assert f['date']['value']=='2026-11-03'
    assert f['signature']['value']=='Елена Викторовна Крылова'
    assert 'elena@example.com' in f['party_details']['value']
    assert '40 000' in f['grounds']['value'] and '5 октября' in f['grounds']['value']
    assert 'платёж не оценён' in f['grounds']['value']
    assert '100 000' in f['requests']['value'] and '60 000' in f['requests']['value']
    assert 'Другие части решения не обжалую' in f['requests']['value']
    assert 'ещё не направляла' in f['copy_notice']['value']
    assert len(f['attachments']['value'].splitlines())==2
    assert f.get('other_participants',{}).get('status')!='not_applicable'
    assert not f.get('fee',{}).get('value')


@pytest.mark.asyncio
@pytest.mark.parametrize('mode',['offline','empty','broken_evidence'])
async def test_full_reply_extracts_all_known_facts_before_next_question(monkeypatch,mode):
    payload={'answers':[]}
    if mode=='broken_evidence':payload={'answers':[
        {'key':'sender','quote':'Елена Викторовна Крылова','evidence':'latest_message'},
        {'key':'court','quote':'Кировский районный суд города Екатеринбурга','evidence':'latest_message'},
        {'key':'other_participants','quote':'Истец — Сергей Павлович Белов','evidence':'latest_message'},
    ]}
    provider=SimpleNamespace(chat_completion=AsyncMock(return_value=SimpleNamespace(content=json.dumps(payload),usage=TokenUsage(0,0,0,False))))
    client=AsyncMock(side_effect=RuntimeError('offline')) if mode=='offline' else AsyncMock(return_value=provider)
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client',client)
    result,reply,_=await advance_interview(state(),NARRATIVE)
    assert_facts(result)
    assert result['last_questions']==['other_participants'],reply
    assert 'полное имя' not in reply.lower()


@pytest.mark.asyncio
async def test_saved_large_message_is_recovered_on_natural_recall(monkeypatch):
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client',AsyncMock(side_effect=RuntimeError('offline')))
    initial=state();initial['user_turns']=[PROMPT,NARRATIVE]
    result,reply,_=await advance_interview(initial,'посмотри в предыдущее сообщение')
    assert_facts(result)
    assert result['last_questions']==['other_participants'],reply
    assert initial['fields']=={}


@pytest.mark.asyncio
async def test_next_turn_keeps_labelled_addresses_and_all_known_facts(monkeypatch):
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client',AsyncMock(side_effect=RuntimeError('offline')))
    result,_,_=await advance_interview(state(),NARRATIVE)
    for _ in range(2):
        result,reply,_=await advance_interview(result,'продолжить')
        assert_facts(result)
        assert result['last_questions']==['other_participants'],reply
        assert 'кв. 9' in result['fields']['sender_address']['value']
        assert 'кв. 3' in result['fields']['recipient_address']['value']


def test_role_validation_does_not_confuse_appellant_with_claimant():
    value=state();collect_appeal_facts(value,NARRATIVE)
    assert role_evidence_allowed('recipient','Истец — Сергей Павлович Белов.',value)
    assert role_evidence_allowed('recipient_address','Адрес истца: Екатеринбург, ул. Центральная, д. 14.',value)
    assert not role_evidence_allowed('sender_address','Адрес истца: Екатеринбург, ул. Центральная, д. 14.',value)


def test_claimant_can_be_the_appellant_too():
    value=state()
    text=NARRATIVE.replace('ответчик по гражданскому делу','истец по гражданскому делу').replace('Истец — Сергей','Ответчик — Сергей').replace('Адрес истца:','Адрес ответчика:')
    collect_appeal_facts(value,text)
    assert 'истец' in value['fields']['sender']['value']
    assert 'ответчик' in value['fields']['recipient']['value']
    assert 'Центральная' in value['fields']['recipient_address']['value']


def test_fact_collection_is_idempotent_and_does_not_invent_next_year():
    value=state();collect_appeal_facts(value,NARRATIVE)
    old=deepcopy(value);collect_appeal_facts(value,NARRATIVE)
    assert value==old
    value=state();collect_appeal_facts(value,'Районный суд 20 декабря 2026 года вынес решение. Решение в окончательной форме изготовлено 3 января.')
    assert value['fields']['act_date']['status']=='incomplete'


@pytest.mark.asyncio
async def test_bad_evidence_label_does_not_drop_valid_quotes_in_other_forms(monkeypatch):
    value=new_state('Нужна претензия за услуги')
    value.update(scenario='pretense_debt_services',phase='collecting',last_questions=['agreement'])
    text='Исполнитель передал результат 20 сентября 2026 года. Оплата не поступила.'
    payload={'answers':[{'key':'performance','quote':'Исполнитель передал результат 20 сентября 2026 года','evidence':'latest_message'},
                        {'key':'facts','quote':'Оплата не поступила','evidence':'latest_message'},
                        {'key':'amount','quote':'70000 рублей','evidence':'latest_message'}]}
    provider=SimpleNamespace(chat_completion=AsyncMock(return_value=SimpleNamespace(content=json.dumps(payload,ensure_ascii=False),usage=TokenUsage(0,0,0,False))))
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client',AsyncMock(return_value=provider))
    result,_=await _capture_contextual_facts(value,SCENARIOS[value['scenario']],'agreement',text,force=True)
    assert result['fields']['facts']['value']=='Оплата не поступила'
    assert '20 сентября' in result['fields']['performance']['value']
    assert not result['fields'].get('amount',{}).get('value')
    assert result['fields']['facts']['evidence'] in text


def test_quote_binding_rejects_invented_value_and_ambiguous_repeated_identity():
    assert literal_evidence('70000 рублей','Оплата не поступила.','latest_message') is None
    assert literal_evidence('Иванов Иван Иванович','Истец — Иванов Иван Иванович. Ответчик — Иванов Иван Иванович.','latest_message') is None
    s=state()
    s=apply_updates(s,[FieldUpdate(key='sender',value='Елена Викторовна Крылова',status='filled',evidence='latest_message')],'Я — Елена Викторовна Крылова.')
    assert s['fields']['sender']['value']=='Елена Викторовна Крылова'


def test_intake_is_not_tied_to_fixture_names_or_amounts():
    value=state()
    narrative=NARRATIVE.replace('Елена Викторовна Крылова','Ольга Петровна Волкова').replace('Сергей Павлович Белов','Андрей Сергеевич Смирнов').replace('100 000','180 000').replace('40 000','50 000').replace('60 000','130 000').replace('2-1234/2026','2-987/2026')
    collect_appeal_facts(value,narrative)
    f=value['fields']
    assert f['signature']['value']=='Ольга Петровна Волкова'
    assert 'Андрей Сергеевич Смирнов' in f['recipient']['value']
    assert '50 000' in f['grounds']['value'] and '130 000' in f['requests']['value']
    assert f['case_number']['value']=='2-987/2026'


def test_formal_judgment_is_available_without_editor_and_submission_date_is_preserved():
    from app.services.document_form_composition import local_candidate,_validate_slot
    from app.services.document_drafting import validate_edit
    value=state();collect_appeal_facts(value,NARRATIVE)
    judgment=value['fields']['challenged_act']['value']
    assert local_candidate('challenged_act',judgment,'sentence','appeal_civil')==judgment
    source='Подтверждение перевода я представила суду 5 октября, документ есть в материалах дела.'
    assert validate_edit(source,source)
    assert not validate_edit('Факт перевода подтверждён представленным в материалы дела документом от 5 октября.',source)
    assert not validate_edit('Автор жалобы представила подтверждение перевода суду 5 октября, документ есть в материалах дела.',source)
    assert not _validate_slot('appeal_term','Копия апелляционной жалобы получена мною 27 октября.','Копию решения я получила 27 октября','sentence')
    assert not _validate_slot('requests','Остальные части решения оставляю без изменений.','Другие части решения не обжалую.','sentence')
    assert local_candidate('appeal_term','Копию решения я получила 27 октября','sentence','appeal_civil')=='Копию решения я получила 27 октября.'
    assert local_candidate('copy_notice','Копию жалобы истцу ещё не направляла.','sentence','appeal_civil')=='Копию жалобы истцу ещё не направляла.'


@pytest.mark.asyncio
async def test_editor_does_not_print_purpose_label():
    from app.services.document_slot_editor import edit_slots
    from app.services.document_form_composition import _validate_slot
    provider=SimpleNamespace(chat_completion=AsyncMock(return_value=SimpleNamespace(content='Копия решения мною получена 27 октября. Соблюдение срока обжалования.',usage=TokenUsage(0,0,0,False))))
    data={'appeal_term':{'source_text':'Копию решения я получила 27 октября.','purpose':'Соблюдение срока обжалования','format':'sentence','template_context':[]}}
    valid,_=await edit_slots(provider,data,_validate_slot,document='Апелляционная жалоба')
    assert valid['appeal_term']=='Копия решения мною получена 27 октября.'
