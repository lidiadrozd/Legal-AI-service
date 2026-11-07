from unittest.mock import AsyncMock

import httpx
import pytest

from app.services import gigachat_client
from app.services.document_workflow import advance_interview, new_state, provider_failure_kind


@pytest.mark.asyncio
async def test_reported_loan_intake_works_without_provider(monkeypatch):
    provider = AsyncMock(side_effect=RuntimeError("unavailable"))
    monkeypatch.setattr("app.services.document_workflow.get_gigachat_client", provider)
    prompt = "Нужна претензия: знакомый не вернул 7 тыс руб по расписке"
    state, _, _ = await advance_interview(new_state(prompt), prompt)
    assert state["scenario"] == "pretense_debt_loan" and state["last_questions"] == ["sender"]
    assert state["fields"]["amount"]["value"] == "7000.00"
    for text, next_key in [("Иванов Иван Иванович", "sender_address"),
                           ("Екатеринбург, Блюхера 33, кв 60", "recipient"),
                           ("Петров Пётр Петрович", "recipient_address"),
                           ("Екатеринбург, Мира 50, 70", "agreement"),
                           ("Расписка, заключена 4 сентября", "agreement"),
                           ("2026 год, факт: расписка", "due_date")]:
        state, answer, _ = await advance_interview(state, text)
        assert state["last_questions"] == [next_key], (text, answer)
        assert "pending_answer" not in state
    assert "4 сентября" in state["fields"]["agreement"]["value"]
    assert "2026" in state["fields"]["agreement"]["value"]
    provider.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_receipt_year_retains_known_receipt(monkeypatch):
    state = new_state("Претензия о возврате займа")
    state.update(scenario="pretense_debt_loan", phase="collecting", last_questions=["agreement"])
    from app.services.document_scenarios import SCENARIOS
    state["fields"] = {f.key: {"status": "unknown", "value": None} for f in SCENARIOS[state["scenario"]].fields}
    state["fields"].pop("agreement")
    monkeypatch.setattr("app.services.document_workflow.get_gigachat_client", AsyncMock(side_effect=RuntimeError("offline")))
    state, _, _ = await advance_interview(state, "Расписка от 4 сентября")
    # Keep another field pending so the test does not invoke final drafting.
    state["fields"].pop("due_date")
    state, _, _ = await advance_interview(state, "Год не помню")
    assert state["fields"]["agreement"]["status"] == "filled"
    assert "4 сентября" in state["fields"]["agreement"]["value"]
    assert "[год составления]" in state["fields"]["agreement"]["value"]


@pytest.mark.asyncio
async def test_chat_transport_reuses_client_and_closes_it(monkeypatch):
    original = httpx.AsyncClient
    created = []
    def factory(**kwargs):
        created.append(kwargs)
        return original(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={
            "choices": [{"message": {"content": "готово"}}]})))
    monkeypatch.setattr(gigachat_client.httpx, "AsyncClient", factory)
    monkeypatch.setattr(gigachat_client, "build_gigachat_ssl_context", lambda: True)
    client = gigachat_client.GigaChatAutoToken()
    client.get_valid_token = AsyncMock(return_value="synthetic-token")
    for _ in range(3): await client.chat_completion([], "test-model")
    assert len(created) == 1
    transport = client._http_client
    assert not transport.is_closed
    await client.aclose()
    assert transport.is_closed and client._http_client is None


@pytest.mark.asyncio
async def test_read_timeout_is_not_automatically_replayed(monkeypatch):
    original = httpx.AsyncClient
    calls = []
    def fail(request):
        calls.append(request)
        raise httpx.ReadTimeout("synthetic timeout", request=request)
    monkeypatch.setattr(gigachat_client.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(fail)))
    monkeypatch.setattr(gigachat_client, "build_gigachat_ssl_context", lambda: True)
    client = gigachat_client.GigaChatAutoToken()
    client.get_valid_token = AsyncMock(return_value="synthetic-token")
    with pytest.raises(RuntimeError) as error: await client.chat_completion([], "test-model")
    assert provider_failure_kind(error.value) == "timeout"
    assert len(calls) == 1
    await client.aclose()


@pytest.mark.parametrize("cause,kind", [(httpx.ConnectTimeout("test"), "connection"), (ValueError("bad JSON"), "invalid_response"),
    (gigachat_client.GigaChatAPIError(429), "limit"), (gigachat_client.GigaChatAPIError(401), "authorization")])
def test_failure_types_remain_distinct(cause, kind):
    assert provider_failure_kind(cause) == kind


def test_editor_keeps_dates_and_amounts_and_does_not_receive_unrelated_examples():
    from app.services.document_drafting import _protect_numbers, validate_edit
    from app.core.prompts import LEGAL_SCOPE_RULES
    raw = "Долг 7000 рублей, срок возврата 15.03.2026"
    masked, values = _protect_numbers(raw)
    assert "7000" not in masked and "15.03.2026" not in masked
    restored = masked
    for marker, value in values.items(): restored = restored.replace(marker, value)
    assert restored == raw
    assert validate_edit("Долг 7000 рублей, срок возврата 15 марта 2026 года", raw)
    assert not validate_edit("Долг 7000 рублей, срок возврата 16 марта 2026 года", raw)
    assert not validate_edit("Срок возврата 15.03.2026", raw)
    assert "собирай сведения последовательно" not in LEGAL_SCOPE_RULES
