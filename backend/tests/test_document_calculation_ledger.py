from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.services.document_calculation_ledger import collect_calculation_turn, extract_components, sanitize_calculation
from app.services.document_scenarios import SCENARIOS
from app.services.document_template_library import load_text_package
from app.services.document_workflow import advance_interview, new_state


def damage_state(*, current="amount"):
    state = new_state("Нужен иск о возмещении имущественного ущерба")
    state.update(
        scenario="claim_damage_property",
        phase="collecting",
        last_questions=[current],
        text_package=load_text_package(SCENARIOS["claim_damage_property"]),
    )
    # The real interview reaches the amount question only after the preceding
    # questions have been answered.  Mark them complete here so the async
    # regression can assert that the calculation itself is skipped next.
    for spec in SCENARIOS["claim_damage_property"].fields:
        if spec.key == current:
            break
        state["fields"][spec.key] = {"status": "unknown", "value": None}
    return state


def test_component_amounts_are_summed_transparently_without_inventing_claims():
    state = damage_state()
    changed = collect_calculation_turn(
        state,
        "Ущерб — 128500 рублей, оценка — 7000 рублей, моральный вред — 10000 рублей. Сложи сам.",
        "amount",
    )

    assert {"amount", "calculation"} <= changed
    assert Decimal(state["fields"]["amount"]["value"]) == Decimal("128500")
    calculation = state["fields"]["calculation"]
    assert calculation["status"] == "filled"
    assert "Имущественный ущерб — 128 500 рублей" in calculation["value"]
    assert "Расходы на оценку — 7 000 рублей" in calculation["value"]
    assert "Компенсация морального вреда — 10 000 рублей" in calculation["value"]
    assert "128 500 + 7 000 + 10 000 = 145 500 рублей" in calculation["value"]
    assert state["calculation_ledger"]["total"] == "145500.00"
    assert state["calculation_ledger"]["status"] == "confirmed"
    from app.services.document_form_composition import form_narrative_keys
    assert "calculation" not in form_narrative_keys(state)


def test_repair_cost_confirmed_by_an_appraisal_is_damage_but_the_appraisal_fee_is_valuation():
    items, totals = extract_components(
        "Стоимость восстановительного ремонта по отчёту оценщика составляет 138 400 рублей. "
        "За оценку я заплатила 7 000 рублей, почтовые расходы составили 550 рублей."
    )

    assert totals == []
    assert [(item["kind"], item["value"]) for item in items] == [
        ("damage", "138400.00"),
        ("valuation", "7000.00"),
        ("expenses", "550.00"),
    ]


def test_conflicting_user_total_is_not_silently_exported():
    state = damage_state()
    collect_calculation_turn(
        state,
        "Ущерб — 128500 рублей, оценка — 7000 рублей, моральный вред — 10000 рублей, итого 155000 рублей.",
        "amount",
    )

    calculation = state["fields"]["calculation"]
    assert calculation["status"] == "incomplete"
    assert calculation["value"] is None
    assert "145 500 рублей" in calculation["error"]
    assert "155 000 рублей" in calculation["error"]
    assert state["calculation_ledger"]["status"] == "needs_confirmation"


def test_penalty_or_interest_needs_legal_inputs_not_an_automatic_total():
    state = damage_state()
    collect_calculation_turn(
        state,
        "Ущерб — 100000 рублей, неустойка — 5000 рублей.",
        "amount",
    )

    calculation = state["fields"]["calculation"]
    assert calculation["status"] == "incomplete"
    assert "основание, период просрочки, применяемая ставка" in calculation["error"]
    assert state["fields"]["amount"]["value"] == "100000.00"


def test_same_calculation_path_works_for_a_non_clause_claim_template():
    # This form deliberately uses the legacy/document-editor path rather than
    # the clause composer.  The arithmetic must still be generic.
    state = new_state("Иск о задолженности по аренде")
    state.update(scenario="claim_debt_rent", phase="collecting", last_questions=["amount"])

    changed = collect_calculation_turn(
        state,
        "Основной долг — 60000 рублей, расходы на оценку — 5000 рублей.",
        "amount",
    )

    assert {"amount", "calculation"} <= changed
    assert state["fields"]["amount"]["value"] == "60000.00"
    assert "65 000 рублей" in state["fields"]["calculation"]["value"]
    from app.services.document_drafting import narrative_keys
    assert "calculation" not in narrative_keys(state)


def test_vague_appraiser_reference_requires_the_actual_numbers():
    state = damage_state(current="calculation")
    state["fields"]["calculation"] = {
        "status": "filled",
        "value": "Расчёты по требованиям произведены оценщиком.",
    }

    sanitize_calculation(state)

    assert state["fields"]["calculation"]["status"] == "incomplete"
    assert state["fields"]["calculation"]["value"] is None
    assert "Укажите каждую сумму" in state["fields"]["calculation"]["error"]


@pytest.mark.asyncio
async def test_calculate_it_for_me_with_components_stays_in_the_factual_intake(monkeypatch):
    state = damage_state()
    provider = AsyncMock(side_effect=AssertionError("Concrete arithmetic must not call the provider"))
    monkeypatch.setattr("app.services.document_workflow.get_gigachat_client", provider)

    updated, answer, _ = await advance_interview(
        state,
        "Ущерб — 128500 рублей, оценка — 7000 рублей, моральный вред — 10000 рублей. Сложи сам.",
    )

    assert updated["fields"]["calculation"]["status"] == "filled"
    assert "145 500 рублей" in updated["fields"]["calculation"]["value"]
    assert updated["last_questions"] == ["pretrial"]
    assert answer
    assert not provider.called
