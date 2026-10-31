from decimal import Decimal

from app.services.document_calculation_ledger import collect_calculation_turn


def filled(value):
    return {"status": "filled", "value": value, "original": str(value), "evidence": str(value)}


def rule(plan, identifier):
    return next(item for item in plan["rules"] if item["id"] == identifier)


def test_article_395_request_is_intercepted_before_generic_help_and_asks_only_for_missing_system_data():
    state = {
        "scenario": "claim_debt_loan",
        "revision": 0,
        "fields": {
            "amount": filled("120000.00"),
            "due_date": filled("2026-06-10"),
            "calculation": {"status": "incomplete", "value": None},
        },
    }

    changed = collect_calculation_turn(
        state,
        "Рассчитай проценты по статье 395 ГК РФ по 01.09.2026. Частичных платежей не было.",
        "calculation",
    )

    assert changed == {"calculation"}
    assert state["calculation_facts"]["civil_395"]["start_date"] == "2026-06-11"
    assert state["calculation_facts"]["civil_395"]["end_date"] == "2026-09-01"
    assert state["calculation_facts"]["civil_395"]["partial_payments"] == []
    entry = rule(state["calculation_plan"], "civil_395")
    # The user supplied all personal facts.  The plan must stop for an
    # official rate history, never ask the user to choose a rate or invent it.
    assert entry["status"] == "review_required"
    assert entry["system_action"] == "load_key_rate_history"
    assert state["fields"]["calculation"]["status"] == "incomplete"


def test_consumer_delay_rule_uses_selected_form_policy_and_dates_not_a_user_chosen_rate():
    state = {
        "scenario": "claim_consumer_late_delivery",
        "revision": 0,
        "fields": {
            "amount": filled("85000.00"),
            "delivery_due": filled("2026-09-25"),
            "calculation": {"status": "incomplete", "value": None},
        },
    }

    collect_calculation_turn(
        state,
        "Требую неустойку за просрочку. Рассчитай по 28.10.2026.",
        "calculation",
    )

    plan = state["calculation_plan"]
    entry = rule(plan, "consumer_delay_penalty")
    assert entry["status"] == "calculated"
    assert entry["inputs"]["daily_rate_percent"] == "0.5"
    assert entry["inputs"]["rate_source"].startswith("Статья 23.1")
    penalty = next(item for item in plan["items"] if item["kind"] == "consumer_penalty")
    assert Decimal(penalty["value"]) == Decimal("13600.00")
    assert Decimal(plan["claim_price_total"]) == Decimal("98600.00")
    assert state["fields"]["calculation"]["status"] == "filled"
    assert "13 600 рублей" in state["fields"]["calculation"]["value"]


def test_pretension_without_calculation_slot_keeps_completed_contract_penalty_in_request_field():
    state = {
        "scenario": "pretense_debt_services",
        "revision": 0,
        "fields": {"amount": filled("100000.00")},
    }

    changed = collect_calculation_turn(
        state,
        "Требую договорную неустойку: по пункту 7.2 договора 0,1% за каждый день, 10 дней.",
        "requests",
    )

    assert changed == {"requests"}
    plan = state["calculation_plan"]
    assert rule(plan, "contract_penalty")["status"] == "calculated"
    penalty = next(item for item in plan["items"] if item["kind"] == "penalty")
    assert Decimal(penalty["value"]) == Decimal("1000.00")
    assert state["fields"]["requests"]["status"] == "filled"
    request = state["fields"]["requests"]["value"]
    assert "неустойка — 1 000 рублей" in request.lower()
    assert "Общая сумма требования составляет 101 000 рублей" in request


def test_fixed_alimony_price_is_maintained_after_the_normal_monthly_amount_field_is_saved():
    from app.services.document_formula_intake import synchronize_formula_plan

    state = {
        "scenario": "claim_alimony_fixed",
        "revision": 0,
        "fields": {"monthly_amount": filled("18000.00")},
    }

    plan = synchronize_formula_plan(state)

    assert plan["status"] == "calculated"
    assert plan["claim_price_total"] == "216000.00"
    assert state["fields"]["claim_price"]["status"] == "filled"
    assert state["fields"]["claim_price"]["value"] == "216 000 рублей"


def test_article_395_keeps_multiple_partial_payments_as_facts_and_not_as_the_delay_period():
    state = {
        "scenario": "claim_debt_loan",
        "revision": 0,
        "fields": {
            "amount": filled("120000.00"),
            "due_date": filled("2026-06-10"),
            "calculation": {"status": "incomplete", "value": None},
        },
    }

    changed = collect_calculation_turn(
        state,
        (
            "Рассчитай проценты по статье 395 ГК РФ по 01.09.2026. "
            "Частичные платежи: 20.07.2026 вернул 20 000 рублей; "
            "01.08.2026 погасил 5 000 рублей."
        ),
        "calculation",
    )

    assert changed == {"calculation"}
    facts = state["calculation_facts"]["civil_395"]
    assert facts["start_date"] == "2026-06-11"
    assert facts["end_date"] == "2026-09-01"
    assert facts["partial_payments"] == [
        {"date": "2026-07-20", "amount": "20000.00"},
        {"date": "2026-08-01", "amount": "5000.00"},
    ]


def test_alimony_penalty_accepts_every_literal_installment_in_one_answer():
    state = {
        "scenario": "claim_alimony_penalty",
        "revision": 0,
        "fields": {"calculation": {"status": "incomplete", "value": None}},
    }

    changed = collect_calculation_turn(
        state,
        (
            "Рассчитай неустойку по алиментам: за июнь — 10 000 рублей, "
            "просрочка 30 дней; за июль — 8 000 рублей, просрочка 10 дней."
        ),
        "calculation",
    )

    assert changed == {"calculation"}
    facts = state["calculation_facts"]["alimony_penalty"]
    assert [(item["debt"], item["days"]) for item in facts["installments"]] == [
        ("10000.00", "30"), ("8000.00", "10"),
    ]
    penalty = next(item for item in state["calculation_plan"]["items"] if item["kind"] == "alimony_penalty")
    assert Decimal(penalty["value"]) == Decimal("380.00")


def test_pending_formula_never_consumes_an_unrelated_regular_answer():
    from app.services.document_formula_intake import collect_formula_turn

    state = {
        "scenario": "pretense_debt_services",
        "calculation_plan": {
            "status": "needs_input",
            "current_field": "calculation",
            "unresolved_rule_ids": ["contract_penalty"],
        },
        "fields": {"requests": {"status": "incomplete", "value": None}},
    }

    changed = collect_formula_turn(state, "Требую оплатить основной долг.", "requests")

    assert changed == set()
    assert state["fields"]["requests"]["status"] == "incomplete"


def test_statutory_service_debt_request_keeps_same_turn_principal_and_postage_until_article_395_is_calculated(monkeypatch):
    """Regression for a real mixed answer to a pretension's amount question."""
    def verified_rates(_rule_ids, facts, _fields):
        # The production resolver can only request historical segments after
        # it knows the calculation endpoint.  Keep that real sequencing in
        # the regression instead of letting a test fixture manufacture a
        # complete interval too early.
        if not facts.get("civil_395", {}).get("end_date"):
            return {}
        return {
            "civil_395": {
                "rate_source": "Official CBR history",
                "rate_periods": [
                    {"days": 30, "annual_rate": "10", "day_divisor": 365, "source": "Official CBR history"},
                ],
            },
        }

    monkeypatch.setattr(
        "app.services.document_formula_rate_resolver.resolve_official_rate_data",
        verified_rates,
    )
    state = {
        "scenario": "pretense_debt_services",
        "official_rate_lookup": True,
        "revision": 0,
        "fields": {
            "amount": {"status": "incomplete", "value": None},
            "due_date": filled("2026-09-30"),
            "requests": {"status": "filled", "value": "Требую оплатить основной долг.", "origin": "user"},
        },
    }
    mixed_answer = (
        "50 000 рублей. Прошу помочь рассчитать проценты за просрочку по закону и подготовить претензию. "
        "Также понесла почтовые расходы 350 рублей."
    )

    changed = collect_calculation_turn(state, mixed_answer, "amount")

    assert changed == {"requests"}
    assert state["fields"]["amount"]["value"] == "50000.00"
    assert state["calculation_ledger"]["items"] == [
        {
            "kind": "expenses",
            "label": "Дополнительные расходы",
            "value": "350.00",
            "evidence": "Также понесла почтовые расходы 350 рублей",
        }
    ]
    assert state["calculation_plan"]["current_field"] == "requests"
    assert rule(state["calculation_plan"], "civil_395")["missing"] == ["end_date"]

    changed = collect_calculation_turn(state, "по 31.10.2026", "requests")

    assert changed == {"requests"}
    assert state["calculation_plan"]["status"] == "calculated"
    interest = next(item for item in state["calculation_plan"]["items"] if item["kind"] == "interest")
    assert Decimal(interest["value"]) == Decimal("410.96")
    assert state["calculation_plan"]["recovery_total"] == "50760.96"
    request = state["fields"]["requests"]["value"]
    assert "Требую оплатить основной долг" in request
    assert "410,96" in request
    assert "проценты за пользование чужими денежными средствами" in request.lower()
    assert "общая сумма требования составляет 50 760,96 рублей" in request.lower()
    assert "350 рублей = 350 рублей" not in request
    assert "с учетом начисленных процентов" not in request.lower()
    assert "суммы согласно расчёту" not in request.lower()
