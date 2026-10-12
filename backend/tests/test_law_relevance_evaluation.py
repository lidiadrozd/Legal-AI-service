import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import evaluate_law_relevance as evaluation


@pytest.mark.asyncio
async def test_report_counts_expected_results(monkeypatch, tmp_path):
    cases = json.loads(evaluation.CASES_PATH.read_text(encoding="utf-8"))["cases"]
    monkeypatch.setattr(evaluation, "settings", SimpleNamespace(
        GIGACHAT_MODEL="test-model", GIGACHAT_CLIENT_ID="test", GIGACHAT_CLIENT_SECRET="test"))
    monkeypatch.setattr(evaluation, "REPORT_PATH", tmp_path / "report.json")
    monkeypatch.setattr(evaluation, "get_gigachat_client", AsyncMock())
    def reference_analysis(case):
        expected = case["expected_law"]
        return {"sufficient": expected["sufficient"], "groups": [
            {"conditions": [{"kind": item["kind"],
                              "source_quote": " ".join(item["source_contains"]),
                              "requirement": item["requirement_any"][0]} for item in group]}
            for group in expected["groups"]]}
    assess = AsyncMock(side_effect=[SimpleNamespace(status=c["expected"], reason=c["rationale"],
                                  law_analysis=reference_analysis(c))
                                  for c in cases])
    monkeypatch.setattr(evaluation, "assess_law_change_relevance", assess)
    assert await evaluation.main() == 0
    report = json.loads(evaluation.REPORT_PATH.read_text(encoding="utf-8"))
    assert report["state"] == "completed"
    assert report["passed"] == report["total"] == len(cases)
    assert assess.call_count == len(cases)


@pytest.mark.asyncio
async def test_oauth_error_is_not_a_model_quality_score(monkeypatch, tmp_path):
    monkeypatch.setattr(evaluation, "settings", SimpleNamespace(
        GIGACHAT_MODEL="test-model", GIGACHAT_CLIENT_ID="secret-id", GIGACHAT_CLIENT_SECRET="secret-value"))
    monkeypatch.setattr(evaluation, "REPORT_PATH", tmp_path / "report.json")
    monkeypatch.setattr(evaluation, "get_gigachat_client", AsyncMock(side_effect=RuntimeError("secret-value")))
    assess = AsyncMock()
    monkeypatch.setattr(evaluation, "assess_law_change_relevance", assess)
    assert await evaluation.main() == 2
    text = evaluation.REPORT_PATH.read_text(encoding="utf-8")
    report = json.loads(text)
    assert report["state"] == "connection_error"
    assert report["results"] == []
    assert "passed" not in report
    assert "secret-value" not in text
    assess.assert_not_called()
