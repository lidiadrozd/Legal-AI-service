from unittest.mock import AsyncMock

import pytest

from app.services.document_workflow import advance_interview
from complete_form_cases import make_state


@pytest.mark.asyncio
async def test_ready_document_resumes_explicit_edit_and_article_395_from_saved_facts(monkeypatch):
    """A post-ready formula request must not become a generic GigaChat answer."""
    state = make_state("pretense_debt_services")
    state["fields"]["amount"]["value"] = "50000.00"
    state["fields"]["due_date"]["value"] = "2026-09-30"
    state["fields"]["date"]["value"] = "2026-10-30"
    state["fields"]["response_term"] = {"status": "unknown", "value": None}

    resolved_calls = []

    def verified_rates(rule_ids, facts, fields):
        resolved_calls.append((set(rule_ids), facts, fields))
        source = facts["civil_395"]
        assert fields["amount"]["value"] == "50000.00"
        assert source["start_date"] == "2026-10-01"
        assert source["end_date"] == "2026-10-30"
        return {"civil_395": {"rate_source": "Official CBR history", "rate_periods": [{
            "days": 29, "annual_rate": "10", "day_divisor": 365,
            "source": "Official CBR history",
        }]}}

    gigachat = AsyncMock(side_effect=AssertionError("ready formula route must not consult GigaChat"))
    monkeypatch.setattr("app.services.document_workflow.get_gigachat_client", gigachat)
    monkeypatch.setattr(
        "app.services.document_formula_rate_resolver.resolve_official_rate_data",
        verified_rates,
    )

    updated, answer, _ = await advance_interview(
        state,
        ("дозаполни срок исполнения: 2 недели. и рассчитай мне пожалуйста "
         "задолженность по договору оказания услуг с учетом процентов за нарушение сроков оплаты, по закону"),
    )

    assert gigachat.await_count == 0
    assert resolved_calls and resolved_calls[0][0] == {"civil_395"}
    assert updated["phase"] == "ready"
    assert updated["fields"]["response_term"]["status"] == "filled"
    assert updated["fields"]["response_term"]["value"] == "2 недели"
    assert updated["fields"]["amount"]["value"] == "50000.00"
    assert updated["fields"]["due_date"]["value"] == "2026-09-30"
    rule = next(item for item in updated["calculation_plan"]["rules"] if item["id"] == "civil_395")
    assert rule["status"] == "calculated"
    assert rule["inputs"]["start_date"] == "2026-10-01"
    assert rule["inputs"]["end_date"] == "2026-10-30"
    assert "397,26" in updated["fields"]["requests"]["value"]
    assert "397,26" in answer
    assert "7,5" not in answer
