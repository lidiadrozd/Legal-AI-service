import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.document_workflow import advance_interview, new_state, file_request_kind
from app.services.document_scenarios import SCENARIOS
from app.services.llm_cost import TokenUsage
from app.api.documents import interview_file_reply
from app.services.document_workflow import recover_interview_facts


def collecting():
    state = new_state('Нужна претензия о возврате 7 тыс руб по расписке')
    state.update(scenario='pretense_debt_loan', phase='collecting', last_questions=['due_date'])
    state['fields'] = {'sender': {'status': 'filled', 'value': 'Иванов Иван Иванович'}}
    return state


@pytest.mark.parametrize('message', ['А где файл?', 'Ты мне должен отправить файл с моим окончательным документом', 'Пришли файл'])
def test_file_intents_bypass_consultation(message):
    assert file_request_kind(message)


@pytest.mark.parametrize('message', ['Я отправил файл продавцу', 'Не отправляй файл', 'Что означает файл DOCX?'])
def test_file_mentions_are_not_commands_to_skip_intake(message):
    assert file_request_kind(message) is None


@pytest.mark.asyncio
async def test_explicit_file_request_recovers_user_facts_and_creates_draft(monkeypatch):
    state = collecting()
    state['user_turns'] = ['Срок возврата 20.10.2026']
    usage = TokenUsage(1, 1, 2, False)
    structured = AsyncMock(return_value=SimpleNamespace(content=json.dumps({'updates': [
        {'key': 'due_date', 'source_turns': [2]},
        {'key': 'recipient', 'source_turns': [999]}
    ]}), usage=usage))
    monkeypatch.setattr('app.services.document_workflow._structured', structured)
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client', AsyncMock())
    monkeypatch.setattr('app.services.document_drafting.prepare_document_draft', AsyncMock(return_value=(state, usage)))
    # Isolate drafting: all known values here are identity/date data.
    monkeypatch.setattr('app.services.document_drafting.narrative_keys', lambda s: [])
    consult = AsyncMock(side_effect=AssertionError('File requests must not be answered by the LLM'))
    monkeypatch.setattr('app.services.document_workflow._consult_interview', consult)
    result, answer, _ = await advance_interview(state, 'Пришли файл')
    assert result['phase'] == 'ready'
    assert result['fields']['due_date']['value'] == '2026-10-20'
    assert result['fields']['recipient']['status'] == 'unknown'
    assert result['fields']['sender']['value'] == 'Иванов Иван Иванович'
    assert 'Иванов' not in answer
    consult.assert_not_called()


@pytest.mark.asyncio
async def test_where_file_does_not_silently_skip_pending_questions(monkeypatch):
    state = collecting()
    monkeypatch.setattr('app.services.document_workflow.recover_interview_facts',
                        AsyncMock(return_value=(state, TokenUsage(0, 0, 0, False))))
    result, answer, _ = await advance_interview(state, 'Где файл?')
    assert result['phase'] == 'collecting'
    assert result['last_questions'] == ['sender_address']
    assert 'не могу' not in answer.lower()


@pytest.mark.asyncio
async def test_ready_reply_contains_only_a_real_file_link(monkeypatch):
    chat = SimpleNamespace(id=1, document_workflow={'phase': 'ready'})
    prepare = AsyncMock(return_value=SimpleNamespace(document_id='d25ef304-70b6-4031-b77c-caa5882809dc', filename='document.docx'))
    monkeypatch.setattr('app.api.documents.prepare_interview_file', prepare)
    text = await interview_file_reply(chat, 1, object(), 'DO NOT DISPLAY DOCUMENT BODY')
    assert '/documents/d25ef304-70b6-4031-b77c-caa5882809dc/download' in text
    assert 'DO NOT DISPLAY' not in text


@pytest.mark.asyncio
async def test_failed_file_creation_never_claims_file_is_attached(monkeypatch):
    monkeypatch.setattr('app.api.documents.prepare_interview_file', AsyncMock(side_effect=RuntimeError('offline')))
    text = await interview_file_reply(SimpleNamespace(id=1, document_workflow={'phase': 'ready'}), 1, object(), 'body')
    assert '/download' not in text and 'не удалось' in text


@pytest.mark.asyncio
async def test_recovery_separates_contract_deadline_from_demand_and_rejects_phone_signature(monkeypatch):
    state = collecting()
    state['user_turns'] = ['По расписке должны были вернуть деньги до 20 октября 2026. '
                           'Но теперь по этой претензии пусть вернут долг до 1 ноября 2026.', '+79000000000 test@example.com']
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client', AsyncMock())
    monkeypatch.setattr('app.services.document_workflow._structured', AsyncMock(return_value=SimpleNamespace(
        content=json.dumps({'updates': [{'key': 'due_date', 'source_turns': [2]}, {'key': 'signature', 'source_turns': [3]}]}),
        usage=TokenUsage(0, 0, 0, False))))
    result, _ = await recover_interview_facts(state)
    assert result['fields']['due_date']['value'] == '2026-10-20'
    assert 'signature' not in result['fields']
