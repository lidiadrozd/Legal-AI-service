from copy import deepcopy

import pytest

from app.services.document_quality import quality_issues
from app.services.document_scenarios import SCENARIOS
from app.services.document_template_library import load_text_package
from app.services.document_workflow import new_state


def formula_state(scenario):
    state = new_state("formula guard")
    state.update(scenario=scenario, phase="ready", text_package=load_text_package(SCENARIOS[scenario]))
    state["fields"] = {
        spec.key: {"status": "filled", "value": "Заполнено"}
        for spec in SCENARIOS[scenario].fields
    }
    for spec in SCENARIOS[scenario].fields:
        if spec.kind == "money":
            state["fields"][spec.key]["value"] = "100000.00"
        elif spec.kind == "date":
            state["fields"][spec.key]["value"] = "2026-10-31"
    return state


@pytest.mark.parametrize("field", ["calculation", "claim_price", "fee"])
def test_unresolved_visible_formula_field_blocks_export(field):
    state = formula_state("claim_debt_loan")
    state["fields"][field] = {"status": "review_required", "value": None}

    issues = quality_issues(state)

    assert any(issue["field"] == field and issue["code"] == "unresolved_formula_field" for issue in issues)


def test_explicit_not_applicable_optional_formula_fields_do_not_block_export():
    state = formula_state("claim_consumer_late_delivery")
    state["fields"]["fee"] = {"status": "not_applicable", "value": None}
    state["fields"]["claim_price"] = {"status": "not_applicable", "value": None}

    issues = quality_issues(state)

    assert not any(issue["field"] in {"fee", "claim_price"} for issue in issues)


@pytest.mark.parametrize("status", ["needs_input", "review_required"])
def test_pending_calculation_plan_uses_its_targeted_question(status):
    state = formula_state("claim_debt_loan")
    state["calculation_plan"] = {
        "status": status,
        "unresolved_rule_ids": ["interest_395"],
        "pending_question": "Укажите дату начала просрочки и дату расчёта процентов.",
        "rules": [{"id": "interest_395", "missing": ["due_date"], "question": "fallback"}],
    }

    issues = quality_issues(state)

    assert any(
        issue["field"] == "due_date"
        and issue["code"] == "pending_calculation_plan"
        and issue["question"] == "Укажите дату начала просрочки и дату расчёта процентов."
        for issue in issues
    )


def test_not_requested_calculation_plan_does_not_block_export():
    state = formula_state("claim_debt_loan")
    state["calculation_plan"] = {
        "status": "not_requested",
        "unresolved_rule_ids": ["interest_395"],
    }

    issues = quality_issues(state)

    assert not any(issue["code"] == "pending_calculation_plan" for issue in issues)


@pytest.mark.asyncio
async def test_docx_export_returns_409_before_unresolved_calculation_is_rendered(client, db_session, tmp_path, monkeypatch):
    from app.models.chat import ChatSession
    from app.models.document import Document as StoredDocument
    from sqlalchemy import select
    from complete_form_cases import make_state

    state = deepcopy(make_state("claim_debt_loan"))
    state["fields"]["calculation"] = {"status": "review_required", "value": None}
    monkeypatch.setattr("app.core.config.settings.DOCUMENTS_STORAGE_DIR", str(tmp_path))
    chat = ChatSession(user_id=1, title="formula blocker", document_workflow=state)
    db_session.add(chat)
    await db_session.commit()

    response = await client.post(f"/documents/interviews/{chat.id}/export")

    assert response.status_code == 409
    assert "расчёт" in response.json()["detail"].lower()
    assert not list((await db_session.execute(select(StoredDocument))).scalars())
