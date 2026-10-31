import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.document_workflow import advance_interview, new_state, _capture_contextual_facts
from app.services.llm_cost import TokenUsage
from app.services.document_scenarios import SCENARIOS
from app.services.document_template_library import load_text_package


NARRATIVE = (
    'Я разработала для ООО «Вектор» дизайн сайта по договору № 17 от 1 сентября 2026 года. '
    'Цена услуг 80 000 рублей, аванс 30 000 рублей получен. Акт подписан 20 сентября 2026 года, '
    'остаток 50 000 рублей должен был быть оплачен до 30 сентября 2026 года, но деньги не поступили.'
)


def services_state():
    state = new_state('Хочу подготовить претензию о взыскании задолженности по договору оказания услуг.')
    state.update(scenario='pretense_debt_services', phase='collecting', last_questions=['agreement'])
    state['text_package'] = load_text_package(SCENARIOS['pretense_debt_services'])
    state['fields'].update({
        'sender': {'status': 'filled', 'value': 'Завьялова Анна Викторовна'},
        'sender_address': {'status': 'filled', 'value': 'г. Екатеринбург, ул. Мира, д. 66, кв. 78'},
        'recipient': {'status': 'filled', 'value': 'ООО «Вектор»'},
        'recipient_address': {'status': 'filled', 'value': 'г. Екатеринбург, ул. Ленина, д. 55'},
    })
    return state


@pytest.mark.asyncio
async def test_services_narrative_is_split_offline_without_repeating_known_facts(monkeypatch):
    """The deterministic fallback covers common debt narratives too."""
    monkeypatch.setattr(
        'app.services.document_workflow.get_gigachat_client',
        AsyncMock(side_effect=RuntimeError('offline')),
    )

    state, _, _ = await advance_interview(services_state(), NARRATIVE)

    assert state['fields']['agreement']['value'] == 'Договор № 17 от 1 сентября 2026 года'
    assert 'разработала для ООО «Вектор» дизайн сайта' in state['fields']['performance']['value']
    assert state['fields']['due_date']['value'] == 'до 30 сентября 2026 года'
    assert state['fields']['amount']['value'] == '50000.00'
    assert 'деньги не поступили' in state['fields']['facts']['value'].lower()
    assert state['last_questions'] == ['requests']


@pytest.mark.asyncio
async def test_contextual_extraction_uses_literal_slots_before_single_field_fast_path(monkeypatch):
    """A model-led answer fills every stated template fact, never raw prose."""
    payload = {
        'answers': [
            {'key': 'agreement', 'quote': 'договору № 17 от 1 сентября 2026 года'},
            {'key': 'performance', 'quote': 'Я разработала для ООО «Вектор» дизайн сайта'},
            {'key': 'due_date', 'quote': 'до 30 сентября 2026 года'},
            {'key': 'facts', 'quote': 'но деньги не поступили'},
            {'key': 'amount', 'quote': 'остаток 50 000 рублей'},
        ],
    }
    client = SimpleNamespace(
        chat_completion=AsyncMock(return_value=SimpleNamespace(
            content=json.dumps(payload, ensure_ascii=False), usage=TokenUsage(1, 1, 2, False),
        ))
    )
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client', AsyncMock(return_value=client))

    state, _ = await _capture_contextual_facts(services_state(), SCENARIOS['pretense_debt_services'], 'agreement', NARRATIVE)

    assert state['fields']['agreement']['original'] == 'договору № 17 от 1 сентября 2026 года'
    assert state['fields']['performance']['original'] == 'Я разработала для ООО «Вектор» дизайн сайта'
    assert state['fields']['amount']['value'] == '50000.00'
    assert state['fields']['agreement']['value'] != NARRATIVE
    assert state['fields']['facts']['original'] == 'но деньги не поступили'

