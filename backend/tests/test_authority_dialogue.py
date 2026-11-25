from types import SimpleNamespace
from unittest.mock import AsyncMock
import json

import pytest

from app.services.document_dialogue import normalize_address, has_locality, question_text
from app.services.document_workflow import advance_interview, new_state, normalize_field, _structured
from app.services.document_scenarios import SCENARIOS
from app.services.llm_cost import TokenUsage


def authority(key):
    state = new_state("Доверенность на бабушку")
    state.update(scenario="power_of_attorney", phase="collecting", last_questions=[key])
    return state


@pytest.mark.parametrize("raw,expected", [
    ("Екатеринбург, блюхера 45, 35", "г. Екатеринбург, ул. Блюхера, д. 45, кв. 35"),
    ("Екатеринбург, Мира 44, 39", "г. Екатеринбург, ул. Мира, д. 44, кв. 39"),
    ("г. Екатеринбург, ул. Мира, д. 44, кв. 39", "г. Екатеринбург, ул. Мира, д. 44, кв. 39"),
    ("квартиры № 17 в Екатеринбурге по адресу: ул. Лесная, д. 12", "г. Екатеринбург, ул. Лесная, д. 12, кв. 17"),
    ("екатеринбург, лесная 12 17", "г. Екатеринбург, ул. Лесная, д. 12, кв. 17"),
])
def test_reported_complete_addresses(raw, expected):
    spec = next(f for f in SCENARIOS["power_of_attorney"].fields if f.key == "sender_address")
    value, error = normalize_field(spec, raw)
    assert value == expected and error is None
    assert has_locality(value)
    assert normalize_address(value) == value


def test_address_quote_preserves_street_name_and_locality():
    from app.services.document_addresses import components, address_error
    raw = 'квартиры 14 в доме 18 по улице Садовой в Екатеринбурге'
    value = normalize_address(raw)
    assert components(value) == {'locality': 'Екатеринбург', 'street': 'Садовой', 'house': '18', 'flat': '14'}
    assert normalize_address(value) == value and address_error(value) is None
    assert 'ул. Ице' not in normalize_address('по улице Ахматовой')


def test_short_address_quote_only_expands_in_its_own_component_group():
    from app.services.document_addresses import complete_address_quote
    quote = 'ул. Лесная, д. 12'
    phrase = 'квартиры № 17 в Екатеринбурге по адресу: ' + quote
    narrative = f'Я собственница {phrase}. Меня залил сосед из квартиры № 21.'
    assert complete_address_quote(quote, narrative) == phrase
    assert complete_address_quote(quote, narrative + ' Ответчик проживает по адресу: ' + quote) == quote


@pytest.mark.asyncio
async def test_extractor_keeps_flat_and_city_and_asks_about_correspondence(monkeypatch):
    from app.services.document_workflow import _capture_contextual_facts, interview_message
    from app.services.document_fact_provenance import audit_sensitive_fields
    msg = 'Меня зовут Марина Крылова. Я собственница квартиры № 17 в Екатеринбурге по адресу: ул. Лесная, д. 12.'
    value = 'г. Екатеринбург, ул. Лесная, д. 12, кв. 17'
    state = new_state('Иск о возмещении ущерба от залива квартиры')
    state.update(scenario='claim_damage_flood', phase='collecting', last_questions=['sender'],
                 user_turns=[msg], official_rate_lookup=False)
    short = 'ул. Лесная, д. 12'
    response = {'answers': [{'key': 'sender_address', 'quote': short, 'evidence': short}]}
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client', AsyncMock(return_value=object()))
    monkeypatch.setattr('app.services.document_workflow._structured', AsyncMock(return_value=SimpleNamespace(
        content=json.dumps(response, ensure_ascii=False), usage=TokenUsage(1, 1, 2, False))))
    state, _ = await _capture_contextual_facts(state, SCENARIOS[state['scenario']], 'sender', msg, force=True)
    interview_message(state)
    assert state['fields']['sender_address']['address_candidate']['value'] == value
    exported, _ = audit_sensitive_fields(state)
    assert exported['property_address']['value'] == value


@pytest.mark.asyncio
@pytest.mark.parametrize('reply', ['это мой указанный адрес', 'мой'])
async def test_property_address_reply_can_reuse_own_address(reply):
    state = new_state('Иск о возмещении ущерба от залива квартиры')
    raw = 'г. Екатеринбург, ул. Лесная, д. 12, кв. 17'
    state.update(scenario='claim_damage_flood', phase='collecting', last_questions=['property_address'],
                 official_rate_lookup=False, user_turns=[raw])
    state['fields']['sender_address'] = {'status': 'filled', 'value': raw, 'evidence': raw}
    state, _, _ = await advance_interview(state, reply)
    saved = state['fields']['property_address']
    assert saved['value'] == raw and saved['confirmation'] == reply
    assert 'property_address' not in state['last_questions']


@pytest.mark.asyncio
@pytest.mark.parametrize('reply', ['без понятия', 'допишу позже'])
async def test_unknown_address_reply_advances(reply):
    state = authority('recipient_address')
    state, _, _ = await advance_interview(state, reply)
    assert state['fields']['recipient_address']['status'] == 'unknown'
    assert 'recipient_address' not in state['last_questions']


@pytest.mark.asyncio
async def test_city_only_followup_completes_and_exports_previous_address(monkeypatch):
    from app.services.document_fact_provenance import audit_sensitive_fields
    state = authority('sender_address')
    state['official_rate_lookup'] = False
    state['fields']['sender'] = {'status': 'filled', 'value': 'Иванов Иван Иванович'}
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client', AsyncMock(side_effect=RuntimeError('offline')))
    state, _, _ = await advance_interview(state, 'Садовая 18, 14')
    state, _, _ = await advance_interview(state, 'В Екатеринбурге написано же')
    field = state['fields']['sender_address']
    assert field['value'] == 'г. Екатеринбург, ул. Садовая, д. 18, кв. 14'
    assert field['source_quotes'] == ['Садовая 18, 14', 'В Екатеринбурге написано же']
    exported, _ = audit_sensitive_fields(state)
    assert exported['sender_address']['value'] == field['value']


@pytest.mark.asyncio
async def test_partial_address_followed_by_full_address_does_not_ask_city_again():
    initial = authority("sender_address")
    initial["fields"]["sender"] = {"status": "filled", "value": "Иванов Иван Иванович"}
    state, answer, _ = await advance_interview(initial, "Блюхера 45, 38")
    assert state["fields"]["sender_address"]["status"] == "incomplete"
    assert "не указан населённый пункт" in answer and "Одного города" not in answer
    state, answer, _ = await advance_interview(state, "Екатеринбург, блюхера 45, 35")
    assert state["fields"]["sender_address"]["status"] == "filled"
    assert state["last_questions"] == ["recipient"]
    assert "бабушки" in answer
    assert state["fields"]["sender_address"]["value"].count("Екатеринбург") == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("key,message,expected", [
    ("principal_details", "какие данные?", "паспорт"),
    ("principal_details", "паспорт или что?", "доверителя"),
    ("agent_details", "какие данные?", "представителя"),
])
async def test_passport_questions_answered_without_provider(monkeypatch, key, message, expected):
    unavailable = AsyncMock(side_effect=RuntimeError("offline"))
    monkeypatch.setattr("app.services.document_workflow.get_gigachat_client", unavailable)
    state, answer, _ = await advance_interview(authority(key), message)
    assert expected in answer.lower()
    assert state["last_questions"] == [key] and not state["fields"]
    unavailable.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("key,message", [("powers", "ухаживать за моим ребёнком в период моего отсутствия"),
    ("powers", "заботиться о моём ребёнке и ухаживать за ним"), ("validity", "2 года")])
async def test_reported_answers_preserved_without_provider(monkeypatch, key, message):
    unavailable = AsyncMock(side_effect=RuntimeError("offline"))
    monkeypatch.setattr("app.services.document_workflow.get_gigachat_client", unavailable)
    state, answer, _ = await advance_interview(authority(key), message)
    assert state["fields"][key]["value"] == message
    assert key not in state["last_questions"] and "Ошибка" not in answer
    unavailable.assert_not_called()


def test_names_always_identify_whose_name():
    scenario = SCENARIOS["power_of_attorney"]
    for key, role in [("sender", "доверителя"), ("recipient", "представителя"), ("signature", "доверителя")]:
        spec = next(f for f in scenario.fields if f.key == key)
        assert role in question_text(authority(key), spec)


@pytest.mark.asyncio
async def test_missing_function_call_uses_validated_json_fallback():
    client = SimpleNamespace(chat_completion=AsyncMock(side_effect=[
        RuntimeError("GigaChat did not return the requested structured function"),
        SimpleNamespace(content=json.dumps({"value": "тест"}), usage=TokenUsage(1, 1, 2, False))]))
    reply = await _structured(client, "Return data", {}, {"type": "object", "properties": {"value": {"type": "string"}}})
    assert json.loads(reply.content) == {"value": "тест"}
    assert "structured_function" not in client.chat_completion.call_args.kwargs


@pytest.mark.asyncio
async def test_network_failure_preserves_answer_and_retry_replays_it(monkeypatch):
    state = authority("substitution")
    unavailable = AsyncMock(side_effect=RuntimeError("offline"))
    monkeypatch.setattr("app.services.document_workflow.get_gigachat_client", unavailable)
    correction = "исправь условия передоверия: передоверие не разрешаю"
    updated, answer, _ = await advance_interview(state, correction, prior_user_turns=["старый ответ", correction])
    assert updated["pending_answer"]["message"] == correction
    assert updated["last_questions"] == ["substitution"]
    assert "старый ответ" in updated["user_turns"]
    assert "ответ сохранён" in answer and "RuntimeError" not in answer
    client = SimpleNamespace(chat_completion=AsyncMock(return_value=SimpleNamespace(
        content=json.dumps({"updates": [{"key": "substitution", "status": "filled", "value": "передоверие не разрешаю", "evidence": "передоверие не разрешаю"}], "intent": "answer", "explanation": ""}),
        usage=TokenUsage(1, 1, 2, False))))
    monkeypatch.setattr("app.services.document_workflow.get_gigachat_client", AsyncMock(return_value=client))
    retried, _, _ = await advance_interview(updated, "повтори")
    assert retried["fields"]["substitution"]["value"] == "передоверие не разрешаю"
    assert "pending_answer" not in retried


@pytest.mark.asyncio
async def test_legacy_failed_answer_can_be_replayed_from_message_history(monkeypatch):
    unavailable = AsyncMock(side_effect=RuntimeError("offline"))
    monkeypatch.setattr("app.services.document_workflow.get_gigachat_client", unavailable)
    phrase = "заботиться о моём ребёнке и ухаживать за ним"
    state, answer, _ = await advance_interview(authority("powers"), "повтори", prior_user_turns=[phrase, "повтори"])
    assert state["fields"]["powers"]["value"] == phrase
    unavailable.assert_not_called()
