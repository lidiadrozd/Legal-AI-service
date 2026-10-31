import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.document_workflow import advance_interview, new_state, pending_fields
from app.services.document_scenarios import SCENARIOS
from app.services.document_dialogue import normalize_address, has_locality
from app.services.document_quality import quality_issues, clean_agreement
from app.services.document_drafting import validate_edit
from app.services.llm_cost import TokenUsage
from app.api.documents import interview_file_reply


def state_at(scenario, key):
    state = new_state(SCENARIOS[scenario].title)
    state.update(scenario=scenario, phase='collecting', last_questions=[key], progress_recovered=True)
    fields = list(SCENARIOS[scenario].fields)
    before = [f for f in fields[:next(i for i, f in enumerate(fields) if f.key == key)]]
    state['fields'] = {f.key: {'status': 'unknown', 'value': None} for f in before}
    state['fields']['sender'] = {'status': 'filled', 'value': 'Петров Иван Сергеевич'}
    return state


@pytest.mark.asyncio
@pytest.mark.parametrize('scenario,key,answer', [
    ('pretense_consumer_defective_goods', 'goods_category', 'Замороженные продукты, рыба'),
    ('pretense_consumer_defective_goods', 'consumer_status', 'Для личных нужд'),
    ('power_of_attorney', 'substitution', 'Передоверие запрещено'),
    ('complaint_consumer_agency', 'previous_contact', 'В магазин пока не обращался'),
    ('contract_sale_nonresidential', 'encumbrances', 'Залогов и арендаторов нет'),
])
async def test_all_factual_text_fields_advance_without_general_consultation(monkeypatch, scenario, key, answer):
    provider = AsyncMock(side_effect=AssertionError('A factual answer must not become a consultation'))
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client', provider)
    state, reply, _ = await advance_interview(state_at(scenario, key), answer)
    assert state['fields'][key]['value'] == answer
    assert state['last_questions'] != [key]
    assert state['fields']['sender']['value'] == 'Петров Иван Сергеевич'
    provider.assert_not_called()


@pytest.mark.asyncio
async def test_help_and_acknowledgement_return_to_same_field_with_all_context(monkeypatch):
    state = state_at('pretense_consumer_defective_goods', 'goods_category')
    state['request'] = 'Нужна претензия: испорченная рыба, цена 500 рублей'
    state['user_turns'] = ['Купил в магазине Ромашка', 'Рыба просрочена']
    state['fields']['purchase'] = {'status': 'filled', 'value': 'Рыба за 500 рублей'}
    before = deepcopy(state['fields'])
    client = SimpleNamespace(chat_completion=AsyncMock(return_value=SimpleNamespace(
        content='Категория означает вид товара. Для продуктов достаточно назвать продукт и его вид; марка необязательна, если она неизвестна.',
        usage=TokenUsage(1, 1, 2, False))))
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client', AsyncMock(return_value=client))
    state, reply, _ = await advance_interview(state, 'Что за категория?')
    assert reply.count('?') <= 1 and state['last_questions'] == ['goods_category']
    data = json.loads(client.chat_completion.call_args.args[0][1]['content'])
    assert 'Рыба просрочена' in data['user_evidence']
    assert all('333' not in s['title'] and '131' not in s['title'] for s in data['legal_sources'])
    assert state['fields'] == before
    client.chat_completion.reset_mock()
    state, reply, _ = await advance_interview(state, 'Хорошо')
    assert state['last_questions'] == ['goods_category']
    assert 'госпошлин' not in reply.lower() and 'категор' in reply
    client.chat_completion.assert_not_called()
    state, _, _ = await advance_interview(state, 'Замороженная рыба')
    assert state['fields']['goods_category']['value'] == 'Замороженная рыба'


@pytest.mark.asyncio
async def test_unrequested_court_advice_is_rejected_and_intake_continues(monkeypatch):
    client = SimpleNamespace(chat_completion=AsyncMock(return_value=SimpleNamespace(
        content='Для подачи иска государственная госпошлина по статье 333.36 не взимается. Подготовьте исковое заявление в суд.',
        usage=TokenUsage(1, 1, 2, False))))
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client', AsyncMock(return_value=client))
    state, reply, _ = await advance_interview(state_at('pretense_consumer_defective_goods', 'goods_category'), 'Что сюда написать?')
    assert '333' not in reply and 'госпошлин' not in reply.lower()
    assert state['phase'] == 'collecting' and state['last_questions'] == ['goods_category']


@pytest.mark.asyncio
async def test_ambiguous_complaint_asks_recipient_instead_of_guessing(monkeypatch):
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client', AsyncMock(side_effect=AssertionError('No model needed')))
    prompt = 'Жалоба на товар с истекшим сроком годности'
    state, reply, _ = await advance_interview(new_state(prompt), prompt)
    assert not state['scenario'] and 'Роспотребнадзор' in reply
    state, _, _ = await advance_interview(state, 'Продавцу в магазин')
    assert state['scenario'] == 'pretense_consumer_defective_goods' and state['last_questions'] == ['sender']


def test_address_can_end_with_locality():
    for address in ['Сам магазин на Блюхера 41, екатеринбург', 'Блюхера 41, Екатеринбург', 'Екатеринбург, Блюхера 41']:
        normalized = normalize_address(address)
        assert has_locality(normalized) and 'Блюхера' in normalized
    assert not has_locality(normalize_address('Блюхера 41, 5'))


def test_cross_field_quality_and_editor_role_checks():
    state = state_at('pretense_debt_loan', 'signature')
    state['fields'].update({
        'recipient': {'status': 'filled', 'value': 'Сидоров Павел Иванович'},
        'payment_details': {'status': 'filled', 'value': 'Получатель: Сидоров Павел Иванович, банк Пример'},
        'agreement': {'status': 'filled', 'value': 'Договор с Петровым Иваном Николаевичем'},
    })
    assert {i['code'] for i in quality_issues(state)} == {'counterparty_payee', 'conflicting_identity'}
    assert not validate_edit('Денежные средства заявителем фактически не были возвращены.', 'Он мне не вернул деньги.')
    assert clean_agreement('Расписка от 4 сентября 20__ года.\nУточнение пользователя: 2026 год. Факт: расписка.') == 'Расписка от 4 сентября 2026 года.'


@pytest.mark.asyncio
async def test_recall_request_recovers_prior_fact_instead_of_consulting(monkeypatch):
    state = state_at('pretense_consumer_defective_goods', 'goods_category')
    state['user_turns'] = ['Куплена замороженная рыба']
    client = SimpleNamespace(chat_completion=AsyncMock(return_value=SimpleNamespace(
        content=json.dumps({'updates': [{'key': 'goods_category', 'source_turns': [2]}]}), usage=TokenUsage(1, 1, 2, False))))
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client', AsyncMock(return_value=client))
    state, reply, _ = await advance_interview(state, 'Я уже говорила, посмотри выше')
    assert state['fields']['goods_category']['value'] == 'Куплена замороженная рыба'
    assert state['last_questions'] != ['goods_category']
    assert state['fields']['sender']['value'] == 'Петров Иван Сергеевич'


@pytest.mark.asyncio
async def test_model_cannot_cancel_document_intake(monkeypatch):
    state = state_at('pretense_debt_loan', 'due_date')
    client = SimpleNamespace(chat_completion=AsyncMock(return_value=SimpleNamespace(
        content=json.dumps({'updates': [], 'intent': 'cancel', 'explanation': ''}), usage=TokenUsage(1, 1, 2, False))))
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client', AsyncMock(return_value=client))
    state, reply, _ = await advance_interview(state, 'Срок нужно уточнить по расписке')
    assert state['phase'] == 'collecting' and state['last_questions'] == ['due_date']
    assert 'отменена' not in reply


@pytest.mark.asyncio
async def test_export_blocks_counterparty_bank_details_and_requests_one_correction(client, db_session):
    from app.models.chat import ChatSession
    from app.models.document import Document
    from sqlalchemy import select
    state = new_state('Претензия о возврате займа')
    state.update(scenario='pretense_debt_loan', phase='ready')
    state['fields'] = {f.key: {'status': 'unknown', 'value': None} for f in SCENARIOS[state['scenario']].fields}
    state['fields'].update({'sender': {'status': 'filled', 'value': 'Петров Иван Сергеевич'},
        'recipient': {'status': 'filled', 'value': 'Сидоров Павел Иванович'},
        'payment_details': {'status': 'filled', 'value': 'Получатель Сидоров Павел Иванович, банк Пример'}})
    chat = ChatSession(user_id=1, title='Quality check', document_workflow=state)
    db_session.add(chat)
    await db_session.commit()
    result = await client.post(f'/documents/interviews/{chat.id}/export')
    assert result.status_code == 409
    assert not list((await db_session.execute(select(Document))).scalars())
    answer = await interview_file_reply(chat, 1, db_session, 'unused')
    assert chat.document_workflow['phase'] == 'collecting'
    assert chat.document_workflow['last_questions'] == ['payment_details']
    assert answer.count('?') == 1
    assert chat.document_workflow['fields']['recipient']['value'] == 'Сидоров Павел Иванович'
