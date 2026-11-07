import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.document_workflow import advance_interview, new_state, sanitize_interview
from app.services.document_dialogue import infer_scenario
from app.services.document_scenarios import SCENARIOS
from app.services.document_template_library import load_text_package
from app.services.llm_cost import TokenUsage


@pytest.mark.asyncio
@pytest.mark.parametrize("intent", ["answer", "help"])
async def test_nonresidential_sale_form_is_offered_as_a_complete_catalog_form(monkeypatch, intent):
    prompt = "договор купли-продажи нежилого помещения"
    completion = SimpleNamespace(content=json.dumps({"updates": [], "intent": intent,
        "explanation": "Укажите все данные сторон, цену и объект. Когда оплата? Когда передача?"}),
        usage=TokenUsage(1, 1, 2, False))
    client = SimpleNamespace(chat_completion=AsyncMock(return_value=completion))
    monkeypatch.setattr("app.services.document_workflow.get_gigachat_client", AsyncMock(return_value=client))
    state, answer, _ = await advance_interview(new_state(prompt), prompt)
    assert state['scenario'] == 'contract_sale_nonresidential'
    assert state['last_questions'] == ['sender']
    assert 'продав' in answer.casefold()
    client.chat_completion.assert_not_called()


def test_sale_contract_does_not_replace_a_pretense_and_template_covers_every_field():
    prompt = "Претензия по договору купли-продажи нежилого помещения"
    assert infer_scenario(new_state(prompt), prompt) != "contract_sale_nonresidential"
    scenario = SCENARIOS["contract_sale_nonresidential"]
    package = load_text_package(scenario)
    blocks = " ".join(block["text"] for block in package["blocks"])
    assert all("{{" + field.key + "}}" in blocks for field in scenario.fields)


def test_legacy_sale_misclassified_as_housing_resumes_without_losing_facts():
    state = new_state("договор купли-продажи нежилого помещения")
    state.update(scenario="contract_housing", fields={"sender": {"status": "filled", "value": "Иванов Иван Иванович"},
                 "rent_term": {"status": "filled", "value": "ошибка старой классификации"}})
    clean = sanitize_interview(state)
    assert clean["scenario"] == "contract_sale_nonresidential"
    assert clean["phase"] == "collecting"
    assert clean["fields"]["sender"] == state["fields"]["sender"]
    assert "rent_term" not in clean["fields"]
    assert clean["previous_fields"]["rent_term"] == state["fields"]["rent_term"]
    assert state["scenario"] == "contract_housing"  # input remains intact


def test_legacy_model_checklist_is_presented_as_one_question():
    from app.schemas.document_draft import DocumentClarificationResponse
    from app.services.document_draft_validator import format_document_clarification
    response = DocumentClarificationResponse(status="needs_clarification", questions=["Кто продавец?", "Какова цена?"])
    text = format_document_clarification(response)
    assert "Кто продавец?" in text and "Какова цена?" not in text
