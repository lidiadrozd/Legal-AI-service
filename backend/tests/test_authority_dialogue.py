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
])
def test_reported_complete_addresses(raw, expected):
    spec = next(f for f in SCENARIOS["power_of_attorney"].fields if f.key == "sender_address")
    value, error = normalize_field(spec, raw)
    assert value == expected and error is None
    assert has_locality(value)
    assert normalize_address(value) == value


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
