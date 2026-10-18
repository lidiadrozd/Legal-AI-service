import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.models.law_changes import LawChange
from app.models.user_law_interest import UserLawInterest
from app.services import law_relevance_service as service

def analysis(groups=None):
    result = {"sufficient": True, "summary": "Новый отчёт", "groups": groups or [
        {"id": "g1", "conditions": [{"id": "c1", "requirement": "Действующий ИП",
                                    "source_quote": "ИП"}]}]}
    for group in result["groups"]:
        for condition in group["conditions"]:
            condition.setdefault("kind", "role")
    return result

def assessment(verdict, evidence="Я ИП", condition_id="c1"):
    return {"id": condition_id, "verdict": verdict, "fact": "Факт ситуации",
            "evidence": evidence if verdict != "unknown" else ""}

@pytest.mark.parametrize("verdict,status", [
    ("met", "relevant"), ("not_met", "irrelevant"), ("unknown", "insufficient_data")])
def test_status_derived_from_fixed_conditions(verdict, status):
    result = service._validated_match({"assessments": [assessment(verdict)]}, analysis(), "Я ИП")
    assert result.status == status
    assert result.relevant == (status == "relevant")
    assert result.conditions[0]["requirement"] == "Действующий ИП"

@pytest.mark.parametrize("verdicts,status", [
    (["met", "unknown"], "insufficient_data"), (["met", "not_met"], "irrelevant"),
    (["met", "met"], "relevant")])
def test_all_conditions_inside_group_are_required(verdicts, status):
    groups = [{"id": "g1", "conditions": [
        {"id": cid, "requirement": cid, "source_quote": "ИП"} for cid in ("c1", "c2")]}]
    data = {"assessments": [assessment(v, condition_id=cid) for v, cid in zip(verdicts, ("c1", "c2"))]}
    assert service._validated_match(data, analysis(groups), "Я ИП").status == status

@pytest.mark.parametrize("verdicts,status", [
    (["met", "not_met"], "relevant"), (["not_met", "unknown"], "insufficient_data"),
    (["not_met", "not_met"], "irrelevant")])
def test_alternative_groups_use_or(verdicts, status):
    groups = [{"id": gid, "conditions": [{"id": cid, "requirement": cid, "source_quote": "ИП"}]}
              for gid, cid in (("g1", "c1"), ("g2", "c2"))]
    data = {"assessments": [assessment(v, condition_id=cid) for v, cid in zip(verdicts, ("c1", "c2"))]}
    assert service._validated_match(data, analysis(groups), "Я ИП").status == status

@pytest.mark.parametrize("items", [
    [], [assessment("met", condition_id="other")],
    [assessment("met"), assessment("met")],
    [assessment("met", evidence="Выдуманный факт")], [assessment("met", evidence="")],
    [assessment("invalid")]])
def test_cannot_drop_add_duplicate_conditions_or_invent_evidence(items):
    with pytest.raises(ValueError):
        service._validated_match({"assessments": items}, analysis(), "Я ИП")

def test_quote_normalizes_only_case_and_whitespace():
    data = {"assessments": [assessment("met")]}
    assert service._validated_match(data, analysis(), "я\nИП").relevant
    with pytest.raises(ValueError):
        service._validated_match(data, analysis(), "Я работаю по найму")

@pytest.mark.parametrize("data", [
    {"sufficient": True, "summary": "Изменение", "groups": []},
    {"sufficient": "true", "summary": "Изменение", "groups": []},
    {"sufficient": False, "summary": "Нехватка", "groups": analysis()["groups"]},
    analysis([{"id":"g1","conditions":[{"id":"c1","requirement":"ИП","source_quote":"Выдумка"}]}]),
    analysis([{"id":"g1","conditions":[{"id":"c1","requirement":"ИП","source_quote":"ИП"},
                                      {"id":"c1","requirement":"ИП","source_quote":"ИП"}]}]),
])
def test_invalid_law_analysis_rejected(data):
    with pytest.raises(ValueError):
        service._validate_law_analysis(data, "Новый отчёт для ИП")

def completion(data):
    return SimpleNamespace(content=json.dumps(data))

@pytest.mark.asyncio
async def test_law_stage_has_no_user_data_and_user_stage_cannot_edit_conditions(monkeypatch):
    client = SimpleNamespace(chat_completion=AsyncMock(side_effect=[
        completion(analysis()), completion({"assessments":[assessment("met")]})]))
    monkeypatch.setattr(service, "get_gigachat_client", AsyncMock(return_value=client))
    result = await service.assess_law_change_relevance(
        LawChange(id=1, description="Новый отчёт для ИП"),
        UserLawInterest(id=1, topic_key="tax", topic_label="Налоги", source_excerpt="Старый контекст"),
        user_context="Я ИП")
    assert result.relevant
    calls = client.chat_completion.call_args_list
    assert calls[0].kwargs["structured_function"]["name"] == "extract_law_conditions"
    assert calls[1].kwargs["structured_function"]["name"] == "assess_user_conditions"
    assert calls[1].kwargs["structured_function"]["parameters"]["properties"]["assessments"]["items"]["properties"]["id"]["enum"] == ["c1"]
    law_payload = json.loads(calls[0].kwargs["messages"][1]["content"])
    user_payload = json.loads(calls[1].kwargs["messages"][1]["content"])
    assert "Я ИП" not in json.dumps(law_payload, ensure_ascii=False)
    assert "Старый контекст" not in json.dumps(user_payload, ensure_ascii=False)
    assert user_payload["groups"] == analysis()["groups"]
    assert user_payload["user_statements"] == "Я ИП"
    assert result.law_analysis == analysis()

@pytest.mark.asyncio
async def test_incomplete_change_skips_user_matching(monkeypatch):
    client = SimpleNamespace(chat_completion=AsyncMock(return_value=completion(
        {"sufficient":False,"summary":"Нет содержания изменения","groups":[]})))
    monkeypatch.setattr(service, "get_gigachat_client", AsyncMock(return_value=client))
    result = await service.assess_law_change_relevance(
        LawChange(id=1), UserLawInterest(id=1), user_context="Я ИП")
    assert result.status == "insufficient_data"
    assert client.chat_completion.call_count == 1

@pytest.mark.asyncio
async def test_format_retry_is_bounded(monkeypatch):
    client = SimpleNamespace(chat_completion=AsyncMock(side_effect=[
        completion(analysis()), SimpleNamespace(content="Не JSON"),
        completion({"assessments":[assessment("met")]})]))
    monkeypatch.setattr(service, "get_gigachat_client", AsyncMock(return_value=client))
    result = await service.assess_law_change_relevance(
        LawChange(id=1,description="ИП"), UserLawInterest(id=1), user_context="Я ИП")
    assert result.relevant
    assert client.chat_completion.call_count == 3

@pytest.mark.asyncio
async def test_network_failure_does_not_become_irrelevant(monkeypatch):
    monkeypatch.setattr(service, "get_gigachat_client", AsyncMock(side_effect=RuntimeError("secret-value")))
    result = await service.assess_law_change_relevance(LawChange(id=1), UserLawInterest(id=1))
    assert result.status == "error"
    assert result.relevant is False
    assert result.failure_stage == "connection"
    assert result.error_code == "RuntimeError"
    assert "secret-value" not in repr(result)


@pytest.mark.asyncio
async def test_law_failure_is_reported_without_user_matching(monkeypatch):
    invalid = analysis()
    del invalid["groups"][0]["conditions"][0]["source_quote"]
    client = SimpleNamespace(chat_completion=AsyncMock(return_value=completion(invalid)))
    monkeypatch.setattr(service, "get_gigachat_client", AsyncMock(return_value=client))
    result = await service.assess_law_change_relevance(
        LawChange(id=1, description="ИП"), UserLawInterest(id=1), user_context="Я ИП")
    assert result.status == "error"
    assert result.failure_stage == "law_analysis"
    assert result.error_code == "Missing source quote"
    assert client.chat_completion.call_count == 2


@pytest.mark.parametrize("region_verdict,status", [
    ("met", "relevant"), ("not_met", "irrelevant"), ("unknown", "insufficient_data")])
def test_shared_restriction_remains_required_in_each_alternative(region_verdict, status):
    groups = [
        {"id": "g1", "conditions": [
            {"id": "c1", "requirement": "Роль А", "source_quote": "А"},
            {"id": "c2", "kind": "region", "requirement": "Регион Р", "source_quote": "Р"}]},
        {"id": "g2", "conditions": [
            {"id": "c3", "requirement": "Роль Б", "source_quote": "Б"},
            {"id": "c4", "kind": "region", "requirement": "Регион Р", "source_quote": "Р"}]},
    ]
    data = {"assessments": [assessment(verdict, evidence="Мои сведения", condition_id=cid)
                            for cid, verdict in [("c1", "not_met"), ("c2", region_verdict),
                                                 ("c3", "met"), ("c4", region_verdict)]]}
    assert service._validated_match(data, analysis(groups), "Мои сведения").status == status

@pytest.mark.asyncio
async def test_api_access_error_is_distinguished_from_validation(monkeypatch):
    client = SimpleNamespace(chat_completion=AsyncMock(side_effect=service.GigaChatAPIError(402)))
    monkeypatch.setattr(service, "get_gigachat_client", AsyncMock(return_value=client))
    result = await service.assess_law_change_relevance(
        LawChange(id=1, description="Учебный закон"), UserLawInterest(id=1))
    assert result.status == "error"
    assert result.failure_stage == "law_analysis"
    assert result.error_code == "HTTP 402"
    assert not result.relevant
    assert client.chat_completion.call_count == 1
