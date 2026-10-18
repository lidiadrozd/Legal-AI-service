"""Offline verification of the reference evaluation runner, never real API calls."""
import importlib.util
import json
from pathlib import Path

import pytest

from app.services.law_relevance_service import LawRelevanceResult


@pytest.mark.asyncio
@pytest.mark.parametrize("fixed", [False, True])
async def test_reference_suite_uses_revisions_and_reference_adapter(tmp_path, monkeypatch, fixed):
    backend = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(backend))
    spec = importlib.util.spec_from_file_location("reference_evaluator_test", backend / "evaluate_law_relevance.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    monkeypatch.setattr(runner, "CASES_PATH", backend / "tests/fixtures/law_relevance_references.json")
    monkeypatch.setattr(runner, "REPORT_PATH", tmp_path / "report.json")
    monkeypatch.setattr(runner.settings, "GIGACHAT_CLIENT_ID", "fake")
    monkeypatch.setattr(runner.settings, "GIGACHAT_CLIENT_SECRET", "fake")
    monkeypatch.setattr(runner, "FIXED_LAW_ANALYSIS", fixed)
    calls = []
    expected = ["relevant", "irrelevant", "irrelevant", "insufficient_data"]

    async def fake_client():
        return object()

    async def fake_reference(change, reference, *, user_context, law_analysis=None):
        assert (law_analysis is not None) == fixed
        if fixed:
            assert len(law_analysis["groups"][0]["conditions"]) == 3
        assert "пяти дней" in change.old_version
        assert "семи дней" in change.new_version
        assert reference.article == "7"
        assert reference.situation_excerpt == user_context
        calls.append(reference.id)
        status = expected[len(calls) - 1]
        analysis = {"sufficient": True, "groups": [{"conditions": [
            {"kind": "role", "requirement": "Физическое лицо", "source_quote": "Физическим лицам"},
            {"kind": "activity", "requirement": "Подал обращение", "source_quote": "подавшим обращение"},
            {"kind": "other", "requirement": "Для себя", "source_quote": "для себя"},
        ]}]}
        return LawRelevanceResult(status == "relevant", "Учебный результат", status, law_analysis=analysis)

    async def forbidden_legacy(*args, **kwargs):
        pytest.fail("Reference suite must not use keyword interests")

    monkeypatch.setattr(runner, "get_gigachat_client", fake_client)
    monkeypatch.setattr(runner, "assess_law_reference_relevance", fake_reference)
    monkeypatch.setattr(runner, "assess_law_change_relevance", forbidden_legacy)
    import logging
    previous = logging.root.manager.disable
    try:
        assert await runner.main() == 0
    finally:
        logging.disable(previous)
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert calls == [1, 2, 3, 4]
    assert report["passed"] == 4
    assert report["false_positives"] == 0
    assert report["analysis_origin"] == ("manual_fixture" if fixed else "model")
    assert len(report["fixture_sha256"]) == 64
    assert len(report["checker_sha256"]) == 64
