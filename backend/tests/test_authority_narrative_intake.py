from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
import json
import pytest
from authority_intake_case import PROMPT,NARRATIVE
from app.services.document_workflow import new_state,advance_interview,pending_fields,normalize_field
from app.services.document_conversation import conversational_interview_turn
from app.services.document_scenarios import SCENARIOS
from app.services.document_dialogue import infer_scenario,is_recall_request
from app.services.document_authority_facts import collect_authority_facts,is_authority_request,nominative_agent
from app.services.document_template_library import load_text_package,format_template_fields
from app.services.llm_cost import TokenUsage


def state():
    value=new_state(PROMPT)
    value.update(scenario='power_of_attorney',phase='collecting',last_questions=['sender'],text_package=load_text_package(SCENARIOS['power_of_attorney']))
    return value


def assert_facts(result):
    f=result['fields']
    assert f['sender']['value']=='Мария Олеговна Соколова'
    assert f['recipient']['value']=='Ирина Олеговна Соколова'
    assert 'Учебная' in f['sender_address']['value'] and 'кв. 34' in f['sender_address']['value']
    assert 'Садовая' in f['recipient_address']['value'] and 'кв. 18' in f['recipient_address']['value']
    assert f['principal_details']['status']==f['agent_details']['status']=='unknown'
    assert f['validity']['status']=='filled' and f['validity']['value']=='до 31.12.2026 включительно'
    assert f['substitution']['value']=='без права передоверия'
    assert f['place']['value']=='Екатеринбург'
    assert f['date']['value']=='2026-11-03'
    assert f['signature']['value']=='Мария Олеговна Соколова'
    assert f['form_check']['status']=='review_required'
    p=f['powers']['value']
    for phrase in ['ООО «Вектор»','справку о периоде моей работы','заверенную копию приказа об увольнении','2025 год','подать и подписать заявление','расписаться за получение','Получать деньги','заключать соглашения','другие документы','не должна','ул. Деловая, д. 10']:assert phrase in p
    for phrase in ['Учебная','Садовая','Место составления','Паспортные','вручную','Подписываю','сроком']:assert phrase not in p
    assert {f.key for f in pending_fields(result)}=={'contacts','attachments'}


@pytest.mark.asyncio
async def test_plain_delegation_routes_without_exact_title(monkeypatch):
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client',AsyncMock(side_effect=AssertionError('No classifier needed')))
    result,_,_=await advance_interview(new_state(PROMPT),PROMPT)
    assert result['scenario']=='power_of_attorney'
    assert result['last_questions']==['sender']
    assert not is_authority_request('Я доверяю своей сестре.')
    assert not is_authority_request('Не хочу доверить брату получение документов.')
    assert not is_authority_request('Работодатель не выдаёт мне документы, нужна жалоба.')


@pytest.mark.asyncio
@pytest.mark.parametrize('mode',['offline','empty','malformed'])
async def test_full_narrative_and_followups_keep_every_known_fact(monkeypatch,mode):
    provider=SimpleNamespace(chat_completion=AsyncMock(return_value=SimpleNamespace(content='{"answers":[]}' if mode=='empty' else 'bad-json',usage=TokenUsage(0,0,0,False))))
    client=AsyncMock(side_effect=RuntimeError('offline')) if mode=='offline' else AsyncMock(return_value=provider)
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client',client)
    monkeypatch.setattr('app.services.document_conversation.get_gigachat_client',AsyncMock(side_effect=RuntimeError('offline')))
    result,reply,_=await conversational_interview_turn(state(),NARRATIVE)
    assert_facts(result)
    for message in ['написано выше','уже писала','продолжить']:
        result,reply,_=await conversational_interview_turn(result,message)
        assert_facts(result)
        assert result['last_questions'][0] in {'contacts','attachments'},reply


@pytest.mark.asyncio
async def test_recover_legacy_polluted_fields(monkeypatch):
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client',AsyncMock(side_effect=RuntimeError('offline')))
    initial=state();initial['user_turns']=[PROMPT,NARRATIVE,'написано выше']
    initial['last_questions']=['agent_details']
    initial['fields']={'sender':{'status':'filled','value':'Я — Мария Олеговна Соколова'},'recipient':{'status':'filled','value':'Написано Выше'},'principal_details':{'status':'filled','value':'Я — Мария Олеговна Соколова'},'powers':{'status':'filled','value':NARRATIVE[NARRATIVE.index('получить в'): ]}}
    result,reply,_=await advance_interview(initial,'уже писала')
    assert_facts(result)


def test_idempotent_collection_and_manual_passport_placeholders():
    result=state();collect_authority_facts(result,NARRATIVE)
    old=deepcopy(result);collect_authority_facts(result,NARRATIVE)
    assert old==result
    formatted=format_template_fields(SCENARIOS['power_of_attorney'],result['fields'])
    assert 'паспорт доверителя: серия, номер' in formatted['principal_details']
    assert 'паспорт представителя: серия, номер' in formatted['agent_details']
    assert is_recall_request('написано выше')
    assert nominative_agent('Анне Петровне Ивановой')=='Анна Петровна Иванова'
    assert nominative_agent('Марии Сергеевне Вольской')=='Мария Сергеевна Вольская'
    assert nominative_agent('Любови Петровне Ким')=='Любови Петровне Ким'


def test_validity_accepts_end_date_but_not_invalid_date():
    spec=next(f for f in SCENARIOS['power_of_attorney'].fields if f.key=='validity')
    assert normalize_field(spec,'2 года')==('2 года',None)
    assert normalize_field(spec,'до 31 декабря 2026 года включительно')==('до 31.12.2026 включительно',None)
    assert normalize_field(spec,'до 31 февраля 2026 года')[1]


@pytest.mark.asyncio
async def test_passport_question_cannot_ask_for_known_name(monkeypatch):
    result=state()
    for f in SCENARIOS['power_of_attorney'].fields:result['fields'][f.key]={'status':'unknown','value':None}
    result['fields']['recipient']={'status':'filled','value':'Ирина Олеговна Соколова'}
    result['fields'].pop('agent_details')
    result['last_questions']=['agent_details']
    payload={'field':'agent_details','question':'Какое полное ФИО Ирины Олеговны Соколовой?','explanation':''}
    provider=SimpleNamespace(chat_completion=AsyncMock(return_value=SimpleNamespace(content=json.dumps(payload),usage=TokenUsage(0,0,0,False))))
    monkeypatch.setattr('app.services.document_conversation.get_gigachat_client',AsyncMock(return_value=provider))
    updated,reply,_=await conversational_interview_turn(result,'продолжить')
    assert updated['last_questions']==['agent_details']
    assert 'паспорт' in reply.lower() and 'полное ФИО' not in reply


def test_requested_records_are_not_attachments_and_no_extra_powers_are_added():
    from app.services.document_workflow import apply_updates,FieldUpdate
    from app.services.document_form_composition import _validate_slot,form_presentation_fields
    from app.services.document_authority_facts import authority_powers_candidate
    result=state();collect_authority_facts(result,NARRATIVE)
    result=apply_updates(result,[FieldUpdate(key='attachments',value='справку о доходах за 2025 год',status='filled',evidence=NARRATIVE)],NARRATIVE)
    assert not result['fields'].get('attachments',{}).get('value')
    p=result['fields']['powers']['value']
    candidate=authority_powers_candidate(p)
    assert 'Представитель не уполномочен получать деньги, заключать соглашения' in candidate
    assert 'иных действий' not in candidate
    assert not _validate_slot('powers',candidate+' Совершение иных действий, связанных с получением документов.',p,'sentence')
    result['draft_fields']={'powers':candidate,'substitution':'без права передоверия'}
    assert form_presentation_fields(result)['recipient']['value']=='Ирину Олеговну Соколову'
    assert result['fields']['recipient']['value']=='Ирина Олеговна Соколова'
