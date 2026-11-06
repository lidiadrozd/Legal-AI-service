import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.document_workflow import new_state, advance_interview, _needs_contextual_fact_capture
from app.services.document_conversation import conversational_interview_turn
from app.services.document_scenarios import SCENARIOS

NARRATIVE = ('Я, Денис Игоревич Романов, передал Павлу Андреевичу Фомину 60 000 рублей банковским переводом '
             '1 сентября 2026 года по договору займа № 14. Заём беспроцентный, срок возврата — 30 сентября 2026 года. '
             'Договор предусматривает неустойку 0,1% от непогашенного долга за каждый календарный день просрочки. '
             'По договору платёж уменьшает базу начисления со дня поступления, включая этот день.')


@pytest.fixture
def offline(monkeypatch):
    for module in ('document_workflow', 'document_conversation'):
        monkeypatch.setattr('app.services.' + module + '.get_gigachat_client', AsyncMock(side_effect=RuntimeError('offline')))


@pytest.mark.asyncio
async def test_dense_later_answer_captures_due_date_transfer_and_contract(offline):
    state, _, _ = await advance_interview(new_state('Претензия о возврате займа'), 'Претензия о возврате займа')
    state['last_questions'] = ['agreement']
    state, answer, _ = await advance_interview(state, NARRATIVE)
    assert state['fields']['due_date']['value'] == '2026-09-30'
    assert 'банковским переводом' in state['fields']['transfer']['value']
    assert '№ 14' in state['fields']['agreement']['value']
    assert len(state['fields']['agreement']['value']) < 100
    assert state['loan_facts']['principal'] == '60000.00'
    assert state['calculation_facts']['contract_penalty']['rate_percent'] == '0.1'
    assert 'provider_failure' not in state


@pytest.mark.asyncio
async def test_natural_partial_payment_and_retry_never_return_empty(offline):
    state, _, _ = await advance_interview(new_state('Претензия о возврате займа'), 'Претензия о возврате займа')
    state['last_questions'] = ['agreement']
    state, _, _ = await advance_interview(state, NARRATIVE)
    state['last_questions'] = ['amount']
    state['pending_answer'] = {'message': 'из 60000 он вернул 20000 11 октября', 'questions': ['amount']}
    state['provider_failure'] = {'kind': 'invalid_response', 'attempts': 1}
    state, answer, _ = await conversational_interview_turn(state, 'повтори')
    assert answer.strip()
    assert state['fields']['amount']['value'] == '40000.00'
    assert 'pending_answer' not in state and 'provider_failure' not in state
    assert state['loan_facts']['payments'][0]['date'] is None
    before = deepcopy(state['loan_facts']['payments'])
    state['last_questions'] = ['amount']
    state, answer, _ = await conversational_interview_turn(state, 'из 60000 он вернул 20000 11 октября')
    assert state['loan_facts']['payments'] == before
    assert state['fields']['amount']['value'] == '40000.00'


@pytest.mark.asyncio
async def test_contract_penalty_uses_original_balance_before_payment(offline):
    prompt = ('Претензия о возврате займа. ' + NARRATIVE + ' 11 октября 2026 года вернул 20 000 рублей. '
              'Рассчитай неустойку с 1 по 31 октября 2026 года включительно.')
    state, _, _ = await advance_interview(new_state(prompt), prompt)
    assert state['fields']['amount']['value'] == '40000.00'
    penalty = next(r for r in state['calculation_plan']['rules'] if r['id'] == 'contract_penalty')
    assert penalty['status'] == 'calculated', penalty
    assert penalty['items'][0]['value'] == '1440.00'
    assert '10 дн.' in penalty['formula'] and '21 дн.' in penalty['formula']


def test_dense_answer_is_extracted_even_if_it_ends_with_a_question():
    assert _needs_contextual_fact_capture(SCENARIOS['contract_work'], 'subject',
        'Нужно покрасить стены. Работы с 10 по 20 ноября 2026 года. Цена 45 000 рублей. Краску предоставляет заказчик. Что ещё нужно?')


@pytest.mark.asyncio
async def test_malformed_provider_response_has_nonempty_continuation(offline):
    state, _, _ = await advance_interview(new_state('Претензия о возврате займа'), 'Претензия о возврате займа')
    state['last_questions'] = ['amount']
    state, answer, _ = await conversational_interview_turn(state, 'из общей суммы вернул часть')
    assert answer.strip() and state.get('pending_answer')
    state, answer, _ = await conversational_interview_turn(state, 'повтори')
    assert answer.strip()


@pytest.mark.asyncio
async def test_timeout_in_question_planner_keeps_saved_facts(monkeypatch, offline):
    async def slow():
        await asyncio.sleep(60)
    # A provider that never replies must not keep a document turn open.
    monkeypatch.setattr('app.services.document_conversation.get_gigachat_client', slow)
    state, _, _ = await advance_interview(new_state('Претензия о возврате займа'), 'Претензия о возврате займа')
    state['last_questions'] = ['sender']
    # The outer watchdog fails before the former 120-second provider timeout.
    state, answer, _ = await asyncio.wait_for(conversational_interview_turn(state, 'Денис Игоревич Романов'), timeout=8)
    assert answer.strip()
    assert state['fields']['sender']['value'] == 'Денис Игоревич Романов'
    assert state['question_origin'] == 'fallback'


@pytest.mark.asyncio
async def test_stale_failure_without_pending_answer_is_not_empty(offline):
    state, _, _ = await advance_interview(new_state('Претензия о возврате займа'), 'Претензия о возврате займа')
    state['provider_failure'] = {'kind': 'invalid_response'}
    state, answer, _ = await conversational_interview_turn(state, 'повтори')
    assert answer.strip()


@pytest.mark.asyncio
async def test_formula_question_is_not_replaced_with_generic_requests_question(monkeypatch, offline):
    state, _, _ = await advance_interview(new_state('Претензия о возврате займа'), 'Претензия о возврате займа')
    state['last_questions'] = ['agreement']
    state, _, _ = await advance_interview(state, NARRATIVE)
    planner = AsyncMock(return_value=SimpleNamespace(content=json.dumps({
        'field': 'requests', 'question': 'Какие требования вы предъявляете?', 'explanation': ''}), usage={}))
    monkeypatch.setattr('app.services.document_conversation.get_gigachat_client', AsyncMock(return_value=object()))
    monkeypatch.setattr('app.services.document_conversation._structured', planner)
    state['last_questions'] = ['amount']
    state, answer, _ = await conversational_interview_turn(state, 'из 60000 он вернул 20000 11 октября')
    assert 'В каком году' in answer
    planner.assert_not_awaited()
    state, answer, _ = await conversational_interview_turn(state, '2026')
    assert 'По какую дату' in answer
    state, answer, _ = await conversational_interview_turn(state, '31 октября 2026 года')
    penalty = next(r for r in state['calculation_plan']['rules'] if r['id'] == 'contract_penalty')
    assert penalty['items'][0]['value'] == '1440.00'
    assert state['fields']['amount']['value'] == '40000.00'


def test_annual_partial_payments_are_not_calculated_on_unchanged_principal():
    from app.services.document_formula_registry import build_calculation_plan
    plan = build_calculation_plan('pretense_debt_loan', requested={'contract_penalty'}, facts={
        'contract_penalty': {'principal': '60000', 'rate_percent': '10', 'rate_period': 'year',
            'days': 31, 'day_divisor': 365, 'source': 'Договор займа № 14',
            'partial_payments': [{'amount': '20000', 'date': '2026-10-11'}]}})
    assert plan['rules'][0]['status'] == 'review_required'


@pytest.mark.asyncio
async def test_repeating_payment_after_year_clarification_does_not_subtract_twice(offline):
    state, _, _ = await advance_interview(new_state('Претензия о возврате займа'), 'Претензия о возврате займа')
    state['last_questions'] = ['agreement']
    state, _, _ = await advance_interview(state, NARRATIVE)
    state['last_questions'] = ['amount']
    state, _, _ = await conversational_interview_turn(state, 'из 60000 он вернул 20000 11 октября')
    state, _, _ = await conversational_interview_turn(state, '2026')
    state, _, _ = await conversational_interview_turn(state, 'из 60000 он вернул 20000 11 октября')
    assert len(state['loan_facts']['payments']) == 1
    assert state['fields']['amount']['value'] == '40000.00'


@pytest.mark.asyncio
async def test_multiple_payment_sentences_keep_their_dates(offline):
    prompt = ('Претензия о возврате займа. ' + NARRATIVE + ' 11 октября 2026 года вернул 20 000 рублей. '
              'Он вернул 10 000 рублей 21 октября 2026 года. '
              'Рассчитай неустойку с 1 по 31 октября 2026 года включительно.')
    state, _, _ = await advance_interview(new_state(prompt), prompt)
    assert state['fields']['amount']['value'] == '30000.00'
    penalty = next(r for r in state['calculation_plan']['rules'] if r['id'] == 'contract_penalty')
    assert penalty['items'][0]['value'] == '1330.00'


@pytest.mark.asyncio
async def test_multi_field_answer_ending_with_question_preserves_literal_facts(monkeypatch):
    from app.services.document_workflow import _capture_contextual_facts
    message = ('Нужно покрасить стены. Цена 45 000 рублей. Краску предоставляет заказчик. Что ещё нужно?')
    state = new_state('Нужен договор подряда')
    state.update(scenario='contract_work', last_questions=['subject'])
    extracts = [('subject', 'покрасить стены', 'Нужно покрасить стены'),
                ('amount', '45 000 рублей', 'Цена 45 000 рублей'),
                ('materials', 'Краску предоставляет заказчик', 'Краску предоставляет заказчик')]
    available = {f.key for f in SCENARIOS['contract_work'].fields}
    assert all(key in available for key, _, _ in extracts)
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client', AsyncMock(return_value=object()))
    monkeypatch.setattr('app.services.document_workflow._structured', AsyncMock(return_value=SimpleNamespace(
        content=json.dumps({'answers': [{'key': k, 'quote': v, 'evidence': e} for k, v, e in extracts]}), usage={})))
    state, _ = await _capture_contextual_facts(state, SCENARIOS['contract_work'], 'subject', message)
    assert all(state['fields'][key]['status'] == 'filled' for key, _, _ in extracts)
