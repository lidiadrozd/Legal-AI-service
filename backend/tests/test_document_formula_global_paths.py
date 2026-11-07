from datetime import date
from decimal import Decimal

from app.services.document_calculation_ledger import collect_calculation_turn
from app.services.document_formula_intake import synchronize_formula_plan
from app.services.document_formula_rate_resolver import resolve_official_rate_data
from app.services.document_formula_registry import apply_plan_to_state, build_calculation_plan, managed_formula_facts
from app.services.document_state_duty_policy import state_duty_policy


def filled(value):
    return {"status": "filled", "value": value, "original": str(value), "evidence": str(value)}


def test_official_rate_adapter_splits_the_principal_after_a_partial_payment(monkeypatch):
    monkeypatch.setattr(
        "app.services.document_formula_rate_resolver.cbr_key_rate_history",
        lambda _end: ((date(2026, 1, 1), Decimal("10")),),
    )
    facts = {
        "civil_395": {
            "principal": "100",
            "start_date": "2026-01-01",
            "end_date": "2026-01-05",
            "partial_payments": [{"date": "2026-01-02", "amount": "40"}],
        }
    }

    rate_data = resolve_official_rate_data({"civil_395"}, facts, {"amount": filled("100")})
    periods = rate_data["civil_395"]["rate_periods"]

    assert [(item["principal"], item["days"]) for item in periods] == [("100", 2), ("60", 2)]
    plan = build_calculation_plan("claim_debt_loan", fields={"amount": filled("100")}, requested=["civil_395"], facts={**facts, **rate_data})
    interest = next(item for item in plan["items"] if item["kind"] == "interest")
    assert interest["value"] == "0.08"


def test_live_formula_flow_uses_the_source_adapter_without_asking_for_a_rate(monkeypatch):
    monkeypatch.setattr(
        "app.services.document_formula_rate_resolver.resolve_official_rate_data",
        lambda *_args, **_kwargs: {
            "civil_395": {
                "rate_source": "Official CBR history",
                "rate_periods": [{"days": 82, "annual_rate": "10", "day_divisor": 365, "source": "Official CBR history"}],
            }
        },
    )
    state = {
        "scenario": "claim_debt_loan",
        "official_rate_lookup": True,
        "revision": 0,
        "fields": {
            "amount": filled("120000"),
            "due_date": filled("2026-06-10"),
            "calculation": {"status": "incomplete", "value": None},
        },
    }

    changed = collect_calculation_turn(
        state,
        "\u0420\u0430\u0441\u0441\u0447\u0438\u0442\u0430\u0439 \u043f\u0440\u043e\u0446\u0435\u043d\u0442\u044b \u043f\u043e \u0441\u0442\u0430\u0442\u044c\u0435 395 \u0413\u041a \u0420\u0424 \u043f\u043e 01.09.2026. \u0427\u0430\u0441\u0442\u0438\u0447\u043d\u044b\u0445 \u043f\u043b\u0430\u0442\u0435\u0436\u0435\u0439 \u043d\u0435 \u0431\u044b\u043b\u043e.",
        "calculation",
    )

    assert changed == {"calculation"}
    assert state["calculation_plan"]["status"] == "calculated"
    assert state["fields"]["calculation"]["status"] == "filled"
    rule = next(item for item in state["calculation_plan"]["rules"] if item["id"] == "civil_395")
    assert "Official CBR history" in rule["evidence"]


def test_consumer_defective_goods_penalty_does_not_inherit_delivery_cap():
    state = {
        "scenario": "claim_consumer_defective_goods",
        "revision": 0,
        "fields": {"amount": filled("85000"), "calculation": {"status": "incomplete", "value": None}},
    }

    collect_calculation_turn(
        state,
        "\u0420\u0430\u0441\u0441\u0447\u0438\u0442\u0430\u0439 \u043d\u0435\u0443\u0441\u0442\u043e\u0439\u043a\u0443 \u0441 01.01.2026 \u043f\u043e 20.07.2026.",
        "calculation",
    )

    penalty = next(item for item in state["calculation_plan"]["items"] if item["kind"] == "consumer_penalty")
    assert penalty["value"] == "170000.00"


def test_consumer_penalty_is_never_calculated_for_an_explicit_business_purchase():
    state = {
        "scenario": "claim_consumer_late_delivery",
        "revision": 0,
        "fields": {
            "amount": filled("85000"),
            "consumer_status": filled("для предпринимательской деятельности"),
            "delivery_due": filled("2026-09-25"),
            "calculation": {"status": "incomplete", "value": None},
        },
    }

    collect_calculation_turn(
        state,
        "Рассчитай неустойку с 01.01.2026 по 20.07.2026.",
        "calculation",
    )

    rule = next(item for item in state["calculation_plan"]["rules"] if item["id"] == "consumer_delay_penalty")
    assert rule["status"] == "review_required"
    assert "предприниматель" in rule["review_reason"].lower()
    assert not any(item["kind"] == "consumer_penalty" for item in state["calculation_plan"]["items"])


def test_universal_consumer_formula_asks_for_the_factual_personal_purpose_before_rate_selection():
    state = {
        "scenario": "claim_consumer",
        "revision": 0,
        "fields": {
            "amount": filled("85000"),
            "category": filled("товар"),
            "calculation": {"status": "incomplete", "value": None},
        },
    }

    collect_calculation_turn(
        state,
        "Рассчитай неустойку с 01.01.2026 по 20.07.2026.",
        "calculation",
    )

    rule = next(item for item in state["calculation_plan"]["rules"] if item["id"] == "consumer_delay_penalty")
    assert rule["status"] == "needs_input"
    assert rule["missing"] == ["procedure"]


def test_costs_slot_accepts_one_named_expense_and_reuses_it_in_a_motion():
    state = {"scenario": "motion_costs", "revision": 0, "fields": {"costs": {"status": "incomplete", "value": None}}}

    changed = collect_calculation_turn(state, "\u041f\u043e\u0447\u0442\u043e\u0432\u044b\u0435 \u0440\u0430\u0441\u0445\u043e\u0434\u044b \u2014 350 \u0440\u0443\u0431\u043b\u0435\u0439.", "costs")
    synchronize_formula_plan(state)

    assert changed == {"costs"}
    assert state["calculation_ledger"]["status"] == "confirmed"
    assert state["calculation_plan"]["status"] == "calculated"
    assert "350" in state["fields"]["costs"]["value"]


def test_calculated_pretension_supplements_instead_of_replacing_existing_request():
    state = {
        "scenario": "pretense_debt_services",
        "fields": {
            "amount": filled("100000"),
            "requests": {"status": "filled", "value": "\u0422\u0440\u0435\u0431\u0443\u044e \u043e\u043f\u043b\u0430\u0442\u0438\u0442\u044c \u043e\u0441\u043d\u043e\u0432\u043d\u043e\u0439 \u0434\u043e\u043b\u0433.", "origin": "user"},
        },
    }
    plan = build_calculation_plan(
        "pretense_debt_services",
        fields=state["fields"],
        requested=["contract_penalty"],
        facts={"contract_penalty": {"principal": "100000", "rate_percent": "0.1", "rate_period": "day", "days": 10, "contract_clause": "clause"}},
    )

    apply_plan_to_state(state, plan)

    value = state["fields"]["requests"]["value"]
    assert "\u043e\u0441\u043d\u043e\u0432\u043d\u043e\u0439 \u0434\u043e\u043b\u0433" in value.lower()
    assert "1 000 \u0440\u0443\u0431\u043b\u0435\u0439" in value


def test_contract_template_does_not_activate_litigation_formula_engine():
    state = {"scenario": "contract_services", "fields": {"amount": filled("100000")}}

    changed = collect_calculation_turn(
        state,
        "\u0420\u0430\u0441\u0441\u0447\u0438\u0442\u0430\u0439 \u043f\u0440\u043e\u0446\u0435\u043d\u0442\u044b \u043f\u043e \u0441\u0442\u0430\u0442\u044c\u0435 395 \u0413\u041a \u0420\u0424.",
        "amount",
    )

    assert changed == set()
    assert "calculation_plan" not in state


def test_ordinary_civil_property_claim_gets_the_versioned_state_duty_after_confirmed_arithmetic():
    state = {
        "scenario": "claim_debt_loan",
        "fields": {"amount": filled("120000"), "calculation": {"status": "filled", "value": "calculation"}},
        "calculation_ledger": {
            "status": "confirmed",
            "items": [
                {"kind": "principal", "label": "principal", "value": "120000"},
                {"kind": "expenses", "label": "post", "value": "350", "include_in_claim_price": False},
            ],
        },
    }

    synchronize_formula_plan(state)

    assert state["calculation_plan"]["status"] == "calculated"
    assert state["fields"]["claim_price"]["value"] == "120 000 \u0440\u0443\u0431\u043b\u0435\u0439"
    fee = state["fields"]["fee"]["value"]
    assert "4 600 \u0440\u0443\u0431\u043b\u0435\u0439" in fee
    assert "\u043f\u043e\u0434\u043f\u0443\u043d\u043a\u0442 1 \u043f\u0443\u043d\u043a\u0442\u0430 1 \u0441\u0442\u0430\u0442\u044c\u0438 333.19 \u041d\u041a \u0420\u0424" in fee
    assert "consultant" not in fee.lower() and "\u0440\u0435\u0434\u0430\u043a\u0446" not in fee.lower()


def test_legacy_state_duty_evidence_is_cleaned_before_it_reaches_a_fee_field():
    state = {
        "scenario": "claim_debt_loan",
        "fields": {"fee": {"status": "unknown", "value": None}},
    }
    legacy_plan = {
        "status": "calculated",
        "items": [{
            "kind": "state_duty", "value": "5152",
            "evidence": ("НК РФ, подпункт 1 пункта 1 статьи 333.19 "
                         "(редакция, действующая с 08.09.2024); "
                         "https\\://www\\.consultant.ru/document/cons_doc_LAW_28165/"),
        }],
    }

    apply_plan_to_state(state, legacy_plan)

    fee = state["fields"]["fee"]["value"]
    assert "подпункт 1 пункта 1 статьи 333.19 НК РФ" in fee
    assert "consultant" not in fee.lower() and "редакц" not in fee.lower()


def test_property_duty_policy_does_not_apply_a_new_tariff_to_an_old_document_date():
    state = {
        "scenario": "claim_debt_loan",
        "fields": {"amount": filled("120000"), "date": filled("2020-01-01")},
        "calculation_ledger": {"status": "confirmed", "items": [{"kind": "principal", "value": "120000"}]},
    }

    plan = synchronize_formula_plan(state)

    assert plan["status"] == "review_required"
    duty = next(item for item in plan["rules"] if item["id"] == "state_duty")
    assert "\u0443\u043a\u0430\u0437\u0430\u043d\u043d\u043e\u0439 \u0434\u0430\u0442\u043e\u0439" in duty["review_reason"]


def test_automatic_duty_review_does_not_replace_the_next_ordinary_fact_question():
    state = {
        "scenario": "claim_debt_services",
        "fields": {
            "amount": filled("60000"),
            "procedure": filled("предпринимательская деятельность"),
            "requests": {"status": "unknown", "value": None},
        },
        "calculation_ledger": {"status": "confirmed", "items": [{"kind": "principal", "value": "60000"}]},
    }

    plan = synchronize_formula_plan(state)

    assert plan["status"] == "review_required"
    assert state["fields"]["requests"]["status"] == "unknown"


def test_alimony_penalty_is_included_in_the_alimony_exemption_policy():
    state = {"scenario": "claim_alimony_penalty", "fields": {}}

    facts = managed_formula_facts(state)
    plan = build_calculation_plan(
        "claim_alimony_penalty",
        fields={},
        facts=facts,
    )

    duty = next(item for item in plan["rules"] if item["id"] == "state_duty")
    assert duty["status"] == "calculated"
    assert duty["items"][0]["value"] == "0.00"
    assert "333.36" in duty["evidence"][0]


def test_universal_consumer_form_uses_its_procedure_field_for_personal_use_exemption():
    state = {
        "scenario": "claim_consumer",
        "fields": {
            "procedure": filled("Для личных домашних нужд"),
            "amount": filled("85000"),
        },
    }

    facts = managed_formula_facts(state)

    assert facts["state_duty"]["exempt"] is True


def test_consumer_personal_use_is_not_inferred_when_the_facts_say_resale():
    state = {
        "scenario": "claim_consumer",
        "fields": {
            "procedure": filled("Не для личных нужд, а для перепродажи"),
            "amount": filled("85000"),
        },
    }

    assert managed_formula_facts(state) == {}


def test_general_property_tariff_never_leaks_into_an_appeal_or_arbitration_form():
    assert state_duty_policy({"scenario": "appeal_civil", "fields": {}}) == {}
    assert state_duty_policy({"scenario": "appeal_arbitration", "fields": {}}) == {}
