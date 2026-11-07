"""Regressions for document families, resumable editing and factual fidelity."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest

from app.services.document_dialogue import infer_scenario, scenario_candidates, question_text, leaves_blank
from app.services.document_scenarios import SCENARIOS
from app.services.document_workflow import new_state, sanitize_interview
from app.services.document_drafting import prepare_document_draft, DraftPreparationError, facts_digest
from app.services.document_drafting import validate_edit, canonical_editorial
from app.services.llm_cost import TokenUsage


def test_hesitation_does_not_erase_supplied_facts_and_editor_cannot_invent_gaps():
    assert not leaves_blank('Ну я не знаю. Я работал с 1 февраля по 20 октября 2026 года.')
    assert leaves_blank('не знаю')
    assert not validate_edit('Выплатить [СУММА_A] рублей.', 'Выплатить долг.')
    assert canonical_editorial('requests', 'Перенести заседание на дату после выписки', 'motion_postpone') == 'Прошу перенести заседание на дату после выписки.'


@pytest.mark.parametrize('prompt,expected', [
    ('Жалоба в трудовую инспекцию: не выплатили зарплату 100 тысяч рублей', 'complaint_labor_agency'),
    ('Нужно обращение в инспекцию по труду после увольнения', 'complaint_labor_agency'),
    ('Ходатайство о переносе судебного заседания из-за госпитализации', 'motion_postpone'),
])
def test_explicit_purpose_controls_family(prompt, expected):
    state = new_state(prompt)
    assert infer_scenario(state, '') == expected
    assert expected in scenario_candidates(state)
    assert 'pretense_debt_rent' not in scenario_candidates(state)


def test_wrong_scenario_migration_preserves_evidence_and_separates_employer():
    state = new_state('Жалоба в трудовую инспекцию о невыплате зарплаты')
    state.update(scenario='pretense_debt_rent', phase='ready', last_questions=[])
    state['fields'] = {key: {'status': 'filled', 'value': value} for key, value in {
        'sender': 'Иванов Иван Иванович', 'recipient': 'ООО Ромашка',
        'agreement': 'Работал кладовщиком с 1 февраля по 20 октября 2026 года',
        'property': 'Ничего не передавал', 'facts': 'Зарплата за октябрь не выплачена',
    }.items()}
    before = deepcopy(state)
    fixed = sanitize_interview(state)
    assert state == before
    assert fixed['scenario'] == 'complaint_labor_agency'
    assert fixed['fields']['employer']['value'] == 'ООО Ромашка'
    assert fixed['fields']['recipient']['value'] == 'Государственная инспекция труда'
    assert 'property' not in fixed['fields']
    assert 'кладовщиком' in fixed['fields']['facts']['value']
    assert fixed['previous_fields'] == before['fields']
    assert fixed['phase'] == 'collecting'
    assert sanitize_interview(fixed) == fixed


@pytest.mark.asyncio
async def test_case_number_and_contextual_short_answers_need_no_model():
    state = new_state('Ходатайство об отложении заседания')
    state.update(scenario='motion_postpone', fields={
        'case_number': {'status': 'filled', 'value': '2-2451/2026'},
        'copy_notice': {'status': 'filled', 'value': 'нет ещё'},
        'attachments': {'status': 'filled', 'value': 'справка из больницы'},
    })
    client = SimpleNamespace(chat_completion=AsyncMock(side_effect=AssertionError('No model needed')))
    result, _ = await prepare_document_draft(state, client)
    assert 'case_number' not in result['draft_fields']
    assert 'не направлены' in result['draft_fields']['copy_notice']
    assert result['draft_fields']['attachments'] == 'Справка из больницы.'
    assert result['fields'] == state['fields']
    assert 'иска' not in question_text(state, next(f for f in SCENARIOS['motion_postpone'].fields if f.key == 'copy_notice'))


@pytest.mark.asyncio
async def test_only_rejected_fragments_are_retried_without_publishing_them():
    state = new_state('Претензия о товаре')
    state.update(scenario='pretense_consumer_defective_goods', fields={
        'facts': {'status': 'filled', 'value': 'При использовании телефон перестал работать.'},
        'defect': {'status': 'filled', 'value': 'Не работает экран.'},
    })
    usage = TokenUsage(1, 1, 2, False)
    client = SimpleNamespace(chat_completion=AsyncMock(side_effect=[
        SimpleNamespace(content='В процессе использования телефон перестал работать.', usage=usage),
        SimpleNamespace(content='Экран не функционирует.', usage=usage),
        SimpleNamespace(content='{"supported":{"facts":true,"defect":false}}', usage=usage),
        SimpleNamespace(content='Экран не функционирует.', usage=usage),
        SimpleNamespace(content='{"supported":{"defect":true}}', usage=usage),
    ]))
    with pytest.raises(DraftPreparationError) as error:
        await prepare_document_draft(state, client)
    partial = error.value.partial_state
    assert 'draft_fields' not in partial and error.value.keys == ['defect']
    result, _ = await prepare_document_draft(partial, client)
    assert client.chat_completion.await_count == 5
    assert result['draft_digest'] == facts_digest(state['fields'])
    assert result['fields'] == state['fields']
