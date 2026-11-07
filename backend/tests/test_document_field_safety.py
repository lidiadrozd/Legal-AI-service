from copy import deepcopy

import pytest

from complete_form_cases import make_state
from app.services.document_conversation import conversational_interview_turn
from app.services.document_dialogue import asks_for_help
from app.services.document_field_safety import field_value_problem
from app.services.document_form_composition import _validate_slot, local_candidate
from app.services.document_question_policy import asks_user_to_determine_law
from app.services.document_quality import quality_issues


def test_field_gate_rejects_an_appraisal_instead_of_the_damaged_object():
    answer = "Независимая оценка определила стоимость восстановительного ремонта в 128 500 рублей."
    assert field_value_problem("property", answer) == "property_is_appraisal"
    assert local_candidate("property", answer, "phrase", "claim_damage_property") is None


@pytest.mark.parametrize("key, answer, expected", [
    ("property", "Поврежденное имущество", "property_is_generic"),
    ("damage", "Повреждение имущества:", "damage_is_generic"),
    ("damage", "Обращалась в управляющую компанию, ответа нет", "damage_is_other_fact"),
    ("property_right", "Какое моё право нарушено?", "property_right_is_legal_conclusion"),
])
def test_wrong_field_content_is_never_accepted_as_a_formal_slot(key, answer, expected):
    assert field_value_problem(key, answer) == expected
    assert not _validate_slot(key, answer, answer, "phrase")


def test_quality_gate_reopens_a_field_before_a_document_can_be_exported():
    state = make_state("claim_damage_property")
    state["fields"]["property"] = {
        "status": "filled",
        "value": "Независимая оценка определила стоимость ремонта в 128 500 рублей.",
    }
    issues = quality_issues(state)
    assert any(item["field"] == "property" and item["code"] == "property_is_appraisal" for item in issues)


def test_unpunctuated_party_clarification_is_not_saved_as_an_answer():
    assert asks_for_help("так это обо мне или о компании")


def test_user_is_not_asked_to_choose_a_legal_qualification():
    assert asks_user_to_determine_law("Какое конкретно ваше право на имущество было нарушено?")


@pytest.mark.asyncio
async def test_help_turn_stays_on_same_fact_field_and_never_calls_question_planner(monkeypatch):
    state = make_state("claim_damage_property")
    state["fields"].pop("property_right", None)
    state.update(phase="collecting", last_questions=["property_right"])
    before = deepcopy(state["fields"])
    # The consultation controller falls back to deterministic field guidance.
    async def unavailable():
        raise RuntimeError("offline")
    monkeypatch.setattr("app.services.document_workflow.get_gigachat_client", unavailable)
    result, answer, _ = await conversational_interview_turn(state, "сам посмотри закон и скажи")
    # Normalization may add harmless ``error: None`` keys to older facts, but
    # a request for legal help must not become a new factual answer or alter a
    # previously captured value.
    assert "property_right" not in result["fields"]
    for key, field in before.items():
        assert result["fields"][key].get("value") == field.get("value")
    assert result["last_questions"] == ["property_right"]
    assert "не нужно самостоятельно формулировать" in answer.casefold()
    assert "каком фактическом основании" in answer.casefold()
