import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from copy import deepcopy
import pytest
from app.services.document_workflow import new_state,advance_interview
from app.services.document_conversation import conversational_interview_turn
from app.services.llm_cost import TokenUsage
from complete_form_cases import make_state


@pytest.mark.asyncio
async def test_model_selects_and_words_next_question_without_canned_question_text(monkeypatch):
    state=make_state('contract_employment')
    state.update(phase='collecting',last_questions=['sender'])
    for key in ('sender','recipient'):state['fields'].pop(key)
    state['request']='Договор между детским садом и воспитателем'
    state['fields']['position']['value']='воспитатель'
    seen=[]
    async def structured(client,prompt,data,schema,**kwargs):
        seen.append(data)
        return SimpleNamespace(content=json.dumps({'field':'recipient','question':'Как зовут воспитателя полностью?','explanation':''}),usage=TokenUsage(1,1,2,False))
    monkeypatch.setattr('app.services.document_conversation.get_gigachat_client',AsyncMock(return_value=object()))
    monkeypatch.setattr('app.services.document_conversation._structured',structured)
    result,answer,_=await conversational_interview_turn(state,'продолжить')
    assert answer=='Как зовут воспитателя полностью?'
    assert result['last_questions']==['recipient'] and result['question_origin']=='gigachat'
    assert all('question' not in field for field in seen[0]['missing'])
    assert 'Для школы' not in json.dumps(seen,ensure_ascii=False)


@pytest.mark.asyncio
async def test_example_request_explains_same_field_and_never_fills_it(monkeypatch):
    state=make_state('contract_employment');state['fields'].pop('work_conditions')
    state.update(phase='collecting',last_questions=['work_conditions'])
    before=deepcopy(state['fields'])
    async def structured(client,prompt,data,schema,**kwargs):
        assert data['locked_field']=='work_conditions' and data['help_requested']
        return SimpleNamespace(content=json.dumps({'field':'work_conditions','question':'Какой класс условий труда указан в документах работодателя?','explanation':'Нужны сведения о рабочем месте из результатов СОУТ; неизвестное можно оставить для проверки.'}),usage=TokenUsage(1,1,2,False))
    monkeypatch.setattr('app.services.document_conversation.get_gigachat_client',AsyncMock(return_value=object()))
    monkeypatch.setattr('app.services.document_conversation._structured',structured)
    result,answer,_=await conversational_interview_turn(state,'например')
    assert result['fields']==before and 'work_conditions' not in result['fields']
    assert answer.count('?')==1 and result['last_questions']==['work_conditions']


@pytest.mark.asyncio
async def test_planner_cannot_choose_filled_or_unknown_field(monkeypatch):
    state=make_state('contract_employment');state['fields'].pop('sender');state.update(phase='collecting',last_questions=['sender'])
    async def structured(*args,**kwargs):
        return SimpleNamespace(content='{"field":"invented","question":"Что ещё?","explanation":""}',usage=TokenUsage(1,1,2,False))
    monkeypatch.setattr('app.services.document_conversation.get_gigachat_client',AsyncMock(return_value=object()))
    monkeypatch.setattr('app.services.document_conversation._structured',structured)
    result,_,_=await conversational_interview_turn(state,'продолжить')
    assert result['last_questions']==['sender'] and result['question_origin']=='fallback'


@pytest.mark.asyncio
async def test_address_edit_preserves_street_and_house_and_removes_only_named_apartment():
    state=make_state('contract_employment');state.update(phase='collecting',last_questions=['sender_address'])
    state['fields']['sender_address']={'status':'incomplete','value':'ул. Вилонова, д. 56, кв. 89','error':'Не указан город'}
    state,_,_=await advance_interview(state,'89 писать не надо, это случайность. городо Екатеринбург')
    address=state['fields']['sender_address']
    assert address['status']=='filled' and 'Екатеринбург' in address['value']
    assert 'Вилонова' in address['value'] and '56' in address['value'] and '89' not in address['value']


def test_basic_employment_synonym_and_neutral_fallback():
    from app.services.document_workflow import normalize_field
    from app.services.document_scenarios import SCENARIOS
    fields={f.key:f for f in SCENARIOS['contract_employment'].fields}
    assert normalize_field(fields['employment_type'],'основная')[0]=='основная работа'
    assert 'школ' not in fields['sender'].question.casefold()
    assert 'классах' not in fields['job_function'].question.casefold()
