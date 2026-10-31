from decimal import Decimal

from app.services.document_formula_registry import (
    CALCULATED,
    NEEDS_INPUT,
    REVIEW_REQUIRED,
    apply_plan_to_state,
    build_calculation_plan,
    calculation_is_blocking,
    detect_requested_rules,
    first_pending_question,
)
from app.services.document_form_composition import _confirmed_calculation_text


def filled(value):
    return {"status": "filled", "value": value}


def test_detects_formula_kind_for_every_supported_family_without_a_template_specific_branch():
    assert "civil_395" in detect_requested_rules("claim_debt_loan", "Прошу проценты по статье 395 ГК РФ.")
    assert "civil_395" in detect_requested_rules("claim_debt_loan", "Прошу проценты по ст. 395 ГК РФ.")
    assert "consumer_delay_penalty" in detect_requested_rules("pretense_consumer_late_delivery", "Требую неустойку за просрочку.")
    assert "labor_delay_236" in detect_requested_rules("claim_labor_salary", "Нужна компенсация за задержку зарплаты.")
    assert "labor_delay_236" in detect_requested_rules("claim_labor_salary", "Прошу компенсацию по статье 236 ТК РФ.")
    assert "alimony_penalty" in detect_requested_rules("claim_alimony_penalty", "Взыскать неустойку по алиментам.")
    assert "contract_penalty" in detect_requested_rules("claim_debt_services", "Нужна договорная неустойка.")


def test_explicit_statutory_delay_interest_is_article_395_without_reclassifying_bare_or_consumer_requests():
    statutory = detect_requested_rules(
        "pretense_debt_services",
        "Прошу рассчитать проценты за просрочку по закону.",
    )
    assert "civil_395" in statutory
    assert "interest_basis" not in statutory

    # The legal basis remains a question when a person merely says
    # "проценты".  Consumer delay sanctions remain on their own statutory
    # path rather than being accidentally recast as Article 395.
    assert "civil_395" not in detect_requested_rules("claim_debt_loan", "Прошу взыскать проценты.")
    consumer = detect_requested_rules("pretense_consumer_late_delivery", "Требую неустойку за просрочку по закону.")
    assert "consumer_delay_penalty" in consumer
    assert "civil_395" not in consumer


def test_ambiguous_generic_interest_or_penalty_never_picks_a_legal_rule_at_random():
    interest = build_calculation_plan("claim_debt_loan", text="Прошу взыскать проценты.")
    penalty = build_calculation_plan("claim_debt_loan", text="Прошу взыскать неустойку.")

    assert interest["status"] == NEEDS_INPUT
    assert next(rule for rule in interest["rules"] if rule["id"] == "interest_basis")["status"] == NEEDS_INPUT
    assert penalty["status"] == NEEDS_INPUT
    assert next(rule for rule in penalty["rules"] if rule["id"] == "penalty_basis")["status"] == NEEDS_INPUT


def test_arithmetic_plan_uses_a_ledger_from_any_current_field_and_does_not_need_a_calculation_slot():
    plan = build_calculation_plan(
        "pretense_debt_services",
        fields={"amount": filled("120000")},
        calculation_ledger={
            "items": [
                {"kind": "principal", "label": "Основной долг", "value": "120000", "evidence": "акт"},
                {"kind": "expenses", "label": "Почтовые расходы", "value": "350", "evidence": "чек"},
            ]
        },
        current="requests",
    )

    assert plan["status"] == CALCULATED
    assert plan["current_field"] == "requests"
    assert plan["recovery_total"] == "120350.00"
    assert plan["claim_price_total"] == "120000.00"
    assert [rule["id"] for rule in plan["rules"]] == ["arithmetic_components"]


def test_ledger_expense_keeps_the_principal_from_the_ordinary_amount_field():
    plan = build_calculation_plan(
        "pretense_debt_services",
        fields={"amount": filled("50000")},
        calculation_ledger={
            "items": [{"kind": "expenses", "label": "Почтовые расходы", "value": "350"}],
        },
        current="requests",
    )

    assert plan["claim_price_total"] == "50000.00"
    assert plan["recovery_total"] == "50350.00"
    assert [item["kind"] for item in plan["items"]] == ["principal", "expenses"]


def test_mirrored_base_damage_is_counted_once_and_state_duty_is_not_a_claim_component():
    """Old chats can store one repair cost in two compatible field shapes.

    The durable ledger calls it a principal amount, whereas an earlier
    calculation slot calls it damage.  The export must preserve assessment
    and postal costs, but it must not duplicate the repair cost or add the
    procedural state duty to the monetary-demand equation.
    """
    fields = {
        "amount": filled("138400"),
        "calculation": {
            "status": "filled",
            "value": "",
            "components": [
                {"kind": "damage", "label": "Имущественный ущерб", "value": "138400"},
                {"kind": "valuation", "label": "Расходы на оценку", "value": "7000"},
                {"kind": "expenses", "label": "Почтовые расходы", "value": "550"},
            ],
        },
    }
    plan = build_calculation_plan(
        "claim_damage_property",
        fields=fields,
        calculation_ledger={
            "items": [{"kind": "principal", "label": "Основная сумма требования", "value": "138400"}],
        },
        requested=["arithmetic_components"],
    )

    assert [item["kind"] for item in plan["items"]] == ["principal", "valuation", "expenses"]
    assert plan["claim_price_total"] == "138400.00"
    assert plan["recovery_total"] == "145950.00"

    # A migrated persisted plan may still contain both names and a legacy
    # state-duty flag.  Rendering is defensive and produces one transparent
    # recovery equation in either state.
    rendered = _confirmed_calculation_text(
        {
            "calculation_plan": {
                "status": "calculated",
                "items": [
                    *plan["items"],
                    {"kind": "damage", "label": "Имущественный ущерб", "value": "138400.00"},
                    {
                        "kind": "state_duty",
                        "label": "Государственная пошлина",
                        "value": "5152.00",
                        "include_in_claim_price": True,
                        "include_in_recovery_total": True,
                    },
                ],
            },
        },
        fields,
    )

    assert rendered is not None
    assert "138 400 + 7 000 + 550 = 145 950 рублей" in rendered
    assert "5 152" not in rendered
    assert rendered.count("138 400 +") == 1


def test_civil_395_is_calculated_only_from_injected_verified_rate_segments():
    plan = build_calculation_plan(
        "claim_debt_loan",
        fields={"amount": filled("120000")},
        requested=["civil_395"],
        facts={
            "civil_395": {
                "principal": "120000",
                "rate_periods": [
                    {"days": 30, "annual_rate": "10", "day_divisor": 365, "source": "Проверенная выгрузка Банка России"}
                ],
                "rate_source": "Проверенная выгрузка Банка России",
            }
        },
    )

    interest = next(item for item in plan["items"] if item["kind"] == "interest")
    assert plan["status"] == CALCULATED
    assert interest["value"] == "986.30"
    assert plan["claim_price_total"] == "120986.30"
    assert "30 дн." in next(rule for rule in plan["rules"] if rule["id"] == "civil_395")["formula"]


def test_civil_395_never_treats_an_unverified_rate_as_official_data():
    plan = build_calculation_plan(
        "claim_debt_loan",
        fields={"amount": filled("120000")},
        requested=["civil_395"],
        facts={
            "civil_395": {
                "principal": "120000",
                "start_date": "2026-06-11",
                "end_date": "2026-09-01",
                "rate_periods": [{"days": 30, "annual_rate": "10", "day_divisor": 365}],
            }
        },
    )

    entry = next(rule for rule in plan["rules"] if rule["id"] == "civil_395")
    assert entry["status"] == REVIEW_REQUIRED
    assert not any(item["kind"] == "interest" for item in plan["items"])
    assert calculation_is_blocking(plan)


def test_civil_395_asks_only_for_the_calculation_endpoint_when_the_due_date_is_known():
    plan = build_calculation_plan(
        "pretense_debt_services",
        fields={"amount": filled("50000")},
        requested=["civil_395"],
        facts={"civil_395": {"principal": "50000", "start_date": "2026-10-01"}},
    )

    entry = next(rule for rule in plan["rules"] if rule["id"] == "civil_395")
    assert entry["missing"] == ["end_date"]
    assert "фактической оплаты" in entry["question"].lower()
    assert "долг должен был" not in entry["question"].lower()


def test_reapplying_a_calculated_pretension_plan_keeps_one_imperative_demand():
    state = {
        "scenario": "pretense_debt_services",
        "fields": {
            "amount": filled("50000"),
            "requests": {"status": "incomplete", "value": None},
        },
    }
    plan = build_calculation_plan(
        "pretense_debt_services",
        fields=state["fields"],
        calculation_ledger={"items": [{"kind": "expenses", "label": "Дополнительные расходы", "value": "350"}]},
        requested=["civil_395"],
        facts={"civil_395": {
            "principal": "50000",
            "rate_periods": [{"days": 30, "annual_rate": "14", "day_divisor": "365", "source": "CBR"}],
        }},
    )

    apply_plan_to_state(state, plan)
    first = state["fields"]["requests"]["value"]
    apply_plan_to_state(state, plan)

    assert state["fields"]["requests"]["value"] == first
    assert first.startswith("Требую уплатить:")
    assert first.count("Общая сумма требования") == 1


def test_contractual_interest_and_penalty_require_the_contractual_rate_instead_of_substituting_article_395():
    missing = build_calculation_plan(
        "claim_debt_services",
        fields={"amount": filled("100000")},
        requested=["contract_penalty"],
        facts={"contract_penalty": {"principal": "100000", "days": 10}},
    )
    assert next(rule for rule in missing["rules"] if rule["id"] == "contract_penalty")["status"] == NEEDS_INPUT

    plan = build_calculation_plan(
        "claim_debt_services",
        fields={"amount": filled("100000")},
        requested=["contract_penalty"],
        facts={
            "contract_penalty": {
                "principal": "100000", "rate_percent": "0.1", "rate_period": "day", "days": 10,
                "contract_clause": "п. 7.2 договора: 0,1% за каждый день",
            }
        },
    )
    penalty = next(item for item in plan["items"] if item["kind"] == "penalty")
    assert plan["status"] == CALCULATED
    assert penalty["value"] == "1000.00"


def test_consumer_delay_penalty_needs_a_verified_policy_rate_and_honours_a_confirmed_cap():
    unresolved = build_calculation_plan(
        "claim_consumer_late_delivery",
        fields={"amount": filled("85000")},
        requested=["consumer_delay_penalty"],
        facts={"consumer_delay_penalty": {"principal": "85000", "days": 40}},
    )
    assert next(rule for rule in unresolved["rules"] if rule["id"] == "consumer_delay_penalty")["status"] == REVIEW_REQUIRED

    plan = build_calculation_plan(
        "claim_consumer_late_delivery",
        fields={"amount": filled("85000")},
        requested=["consumer_delay_penalty"],
        facts={
            "consumer_delay_penalty": {
                "principal": "85000", "daily_rate_percent": "0.5", "days": 40,
                "cap_amount": "85000", "rate_source": "Проверенная карточка нормы",
            }
        },
    )
    penalty = next(item for item in plan["items"] if item["kind"] == "consumer_penalty")
    assert penalty["value"] == "17000.00"
    assert plan["status"] == CALCULATED


def test_labor_delay_uses_verified_segments_and_a_policy_provided_divisor():
    plan = build_calculation_plan(
        "claim_labor_salary",
        fields={"amount": filled("50000")},
        requested=["labor_delay_236"],
        facts={
            "labor_delay_236": {
                "principal": "50000",
                "rate_periods": [
                    {"days": 10, "key_rate_percent": "15", "day_divisor": 150, "source": "Проверенная история ключевой ставки"}
                ],
                "rate_source": "Проверенная история ключевой ставки",
            }
        },
    )

    item = next(item for item in plan["items"] if item["kind"] == "labor_compensation")
    assert item["value"] == "500.00"
    assert plan["status"] == CALCULATED


def test_fixed_alimony_price_and_alimony_penalty_are_independent_formula_rules():
    annual = build_calculation_plan(
        "claim_alimony_fixed", fields={"monthly_amount": filled("18000")},
    )
    assert annual["status"] == CALCULATED
    assert annual["claim_price_total"] == "216000.00"
    assert next(rule for rule in annual["rules"] if rule["id"] == "fixed_alimony_annual_price")["formula"].endswith("216 000 рублей")

    penalty = build_calculation_plan(
        "claim_alimony_penalty",
        requested=["alimony_penalty"],
        facts={
            "alimony_penalty": {
                "installments": [
                    {"debt": "10000", "daily_rate_percent": "0.1", "days": 30, "rate_source": "Проверенная норма"},
                    {"debt": "8000", "daily_rate_percent": "0.1", "days": 10, "rate_source": "Проверенная норма"},
                ]
            }
        },
    )
    assert next(item for item in penalty["items"] if item["kind"] == "alimony_penalty")["value"] == "380.00"


def test_court_costs_and_state_duty_are_separate_from_the_price_of_claim():
    plan = build_calculation_plan(
        "claim_damage_property",
        fields={"amount": filled("100000")},
        calculation_ledger={
            "items": [
                {"kind": "damage", "label": "Имущественный ущерб", "value": "100000"},
                {"kind": "court_cost", "label": "Почтовые расходы", "value": "350", "include_in_claim_price": False},
            ]
        },
        requested=["court_costs", "state_duty"],
        facts={
            "state_duty": {
                "tariff": {
                    "source": "Проверенный тариф НК РФ",
                    "brackets": [{"up_to": None, "base": "2000", "percent_over": "0"}],
                }
            }
        },
    )

    assert plan["status"] == CALCULATED
    assert plan["claim_price_total"] == "100000.00"
    assert plan["recovery_total"] == "100350.00"
    assert plan["state_duty_total"] == "2000.00"
    assert first_pending_question(plan) is None


def test_state_duty_exemption_needs_a_verified_basis_and_does_not_add_a_recovery_amount():
    plan = build_calculation_plan(
        "claim_consumer_defective_goods",
        requested=["state_duty"],
        facts={"state_duty": {"exempt": True, "exemption_basis": "Проверенное основание льготы"}},
    )

    duty = next(item for item in plan["items"] if item["kind"] == "state_duty")
    assert duty["value"] == "0.00"
    assert plan["recovery_total"] is None
    assert plan["status"] == CALCULATED
