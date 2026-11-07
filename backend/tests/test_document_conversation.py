import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.document_workflow import advance_interview, new_state, normalize_field, sanitize_interview, pending_fields
from app.services.document_scenarios import SCENARIOS
from app.services.document_drafting import validate_edit, presentation_fields, facts_digest
from app.services.llm_cost import TokenUsage


def state_for(key):
    state = new_state("Иск о защите прав потребителей")
    state.update(scenario="claim_consumer", phase="collecting", last_questions=[key])
    state["fields"]["sender"] = {"status": "filled", "value": "Петров Иван Иванович"}
    return state


@pytest.mark.asyncio
@pytest.mark.parametrize("key,message,expected", [
    ("sender_address", "кто такой истец?", "подаёт иск"),
    ("sender_address", "истец?", "подаёт иск"),
    ("party_details", "какие например?", "ИНН"),
    ("seller_response", "поясни вопрос", "продавцу"),
    ("copy_notice", "какого документа?", "этого иска"),
    ("calculation", "66000 стоимость телефона + моральный ущерб, сам посчитай", "определяет суд"),
    ("legal_basis", "не знаю, ты должен лучше в этом разбираться", "моя задача"),
    ("sender_details", "пример паспортных данных", "серия 0000"),
])
async def test_user_questions_receive_guidance_even_if_provider_fails(monkeypatch, key, message, expected):
    state = state_for(key)
    before = deepcopy(state["fields"])
    monkeypatch.setattr("app.services.document_workflow.get_gigachat_client", AsyncMock(side_effect=RuntimeError("network")))
    updated, answer, _ = await advance_interview(state, message)
    assert expected in answer
    assert updated["fields"]["sender"] == before["sender"]
    assert updated["fields"].get(key, {}).get("value") != message
    assert updated["last_questions"] == [key]


@pytest.mark.asyncio
async def test_consultation_uses_plain_text_and_remembers_context(monkeypatch):
    state = state_for("party_details")
    text = "Это дополнительные реквизиты сторон. Например, известный ИНН или СНИЛС гражданина; для организации — ИНН и ОГРН. Неизвестные данные не нужно выдумывать."
    client = SimpleNamespace(chat_completion=AsyncMock(return_value=SimpleNamespace(content=text, usage=TokenUsage(2, 3, 5, False))))
    monkeypatch.setattr("app.services.document_workflow.get_gigachat_client", AsyncMock(return_value=client))
    updated, answer, _ = await advance_interview(state, "какие например?")
    assert answer.startswith(text) and answer.count('?') == 1
    assert updated['last_questions'] == ['party_details']
    assert "structured_function" not in client.chat_completion.call_args.kwargs
    data = json.loads(client.chat_completion.call_args.args[0][1]["content"])
    assert data["facts"]["sender"]["value"] == "Петров Иван Иванович"
    assert updated["fields"].get("party_details") is None


@pytest.mark.asyncio
async def test_known_document_type_is_not_asked_again(monkeypatch):
    state = new_state("Претензия о взыскании 20 тыс руб")
    unavailable = AsyncMock(side_effect=RuntimeError("must not call"))
    monkeypatch.setattr("app.services.document_workflow.get_gigachat_client", unavailable)
    state, answer, _ = await advance_interview(state, state["request"])
    assert "из-за чего" in answer
    state, answer, _ = await advance_interview(state, "претензия")
    assert "из-за чего" in answer and "претензия или иск" not in answer
    assert not unavailable.called


@pytest.mark.asyncio
async def test_incomplete_address_keeps_street_and_accepts_city(monkeypatch):
    state = state_for("sender_address")
    state, answer, _ = await advance_interview(state, "блюхера 39, кв 5")
    assert state["fields"]["sender_address"]["status"] == "incomplete"
    assert "населённый пункт" in answer
    state, _, _ = await advance_interview(state, "екатеринбург")
    assert state["fields"]["sender_address"]["status"] == "filled"
    assert "Екатеринбург" in state["fields"]["sender_address"]["value"]
    assert "Блюхера" in state["fields"]["sender_address"]["value"]


def test_two_digit_year_is_normalized():
    spec = next(f for f in SCENARIOS["claim_consumer"].fields if f.key == "date")
    assert normalize_field(spec, "24.10.26") == ("2026-10-24", None)


def test_legacy_control_replies_cannot_be_exported_as_facts():
    state = state_for("signature")
    state["fields"].update({
        "court": {"status": "filled", "value": "не определилась"},
        "seller_response": {"status": "filled", "value": "поясни вопрос"},
        "calculation": {"status": "filled", "value": "66000 + моральный вред, сам посчитай"},
        "fee": {"status": "filled", "value": "у меня есть чек"}})
    cleaned = sanitize_interview(state)
    assert cleaned["fields"]["court"]["value"] is None
    assert cleaned["fields"]["seller_response"]["status"] == "needs_clarification"
    assert cleaned["fields"]["calculation"]["status"] == "needs_clarification"
    assert "fee" not in {f.key for f in pending_fields(cleaned)}
    assert cleaned["fields"]["fee"]["value"] != "у меня есть чек"


def test_editor_cannot_add_numbers_or_claim_an_examination():
    assert validate_edit("Стоимость товара составляет 66000 рублей.", "Стоимость 66000.00 рублей")
    assert not validate_edit("Экспертизой установлена неисправность.", "Телефон взорвался")
    assert not validate_edit("Взыскать 100000 рублей.", "Цена 66000 рублей")


def test_canonical_copy_preserves_event_and_health_threat_without_guessing():
    from app.services.document_drafting import canonical_editorial
    result = canonical_editorial("violation", "телефон взорвался и чуть не поколечил меня", "claim_consumer")
    assert "взрыв телефона" in result and "угрозу" in result
    assert "травма получена" not in result and "пожар" not in result
    assert canonical_editorial("facts", "Экспертиза установила другую причину", "claim_consumer") is None
    assert canonical_editorial("purchase", "книга для себя", "claim_consumer") is None


def test_editor_must_not_replace_explosion_with_fire():
    assert not validate_edit("Произошло возгорание устройства.", "телефон взорвался")


def test_editorial_layer_never_replaces_original_facts_and_invalidates_on_edit():
    state = state_for("facts")
    state["fields"]["facts"] = {"status": "filled", "value": "телефон взорвался"}
    state["draft_fields"] = {"facts": "При эксплуатации телефона произошёл взрыв."}
    state["draft_digest"] = facts_digest(state["fields"])
    from app.services.document_export_contract import EDITOR_VERSION
    state['draft_version'] = EDITOR_VERSION
    assert presentation_fields(state)["facts"]["value"].startswith("При эксплуатации")
    assert state["fields"]["facts"]["value"] == "телефон взорвался"
    state["fields"]["facts"]["value"] = "телефон перестал включаться"
    assert presentation_fields(state)["facts"]["value"] == "телефон перестал включаться"


@pytest.mark.asyncio
async def test_export_uses_checked_editorial_layer_and_retains_originals(client, db_session, tmp_path, monkeypatch):
    from app.models.chat import ChatSession
    from app.models.document import Document
    from app.services.document_template_library import load_text_package
    from io import BytesIO
    from docx import Document as WordDocument
    state = new_state("Претензия о возврате займа")
    state.update(scenario="pretense_debt_loan", phase="ready")
    state["text_package"] = load_text_package(SCENARIOS[state["scenario"]])
    state["fields"] = {f.key: {"status": "unknown", "value": None} for f in SCENARIOS[state["scenario"]].fields}
    raw = "знакомый не вернул 7000 рублей"
    edited = "Заемщик не возвратил денежные средства в размере 7000 рублей."
    state["fields"]["facts"] = {"status": "filled", "value": raw}
    state["fields"]["amount"] = {"status": "filled", "value": "7000.00"}
    fake = SimpleNamespace(chat_completion=AsyncMock(side_effect=[
        SimpleNamespace(content=edited, usage=TokenUsage(1, 1, 2, False)),
        SimpleNamespace(content=json.dumps({'facts':{'meaning_preserved':True,'business_style':True,'fits_context':True,'reason':'checked'}}), usage=TokenUsage(1, 1, 2, False))]))
    monkeypatch.setattr("app.services.gigachat_client.get_gigachat_client", AsyncMock(return_value=fake))
    monkeypatch.setattr("app.core.config.settings.DOCUMENTS_STORAGE_DIR", str(tmp_path))
    chat = ChatSession(user_id=1, title="Editorial export", document_workflow=state)
    db_session.add(chat)
    await db_session.commit()
    response = await client.post(f"/documents/interviews/{chat.id}/export")
    assert response.status_code == 201, response.text
    document_id = response.json()["document_id"]
    downloaded = await client.get(f"/documents/{document_id}/download")
    output = "\n".join(p.text for p in WordDocument(BytesIO(downloaded.content)).paragraphs)
    assert 'Заемщик не возвратил денежные средства в размере 7 000 рублей.' in output and raw not in output
    record = await db_session.get(Document, document_id)
    assert record.generation_meta["fields"]["facts"]["value"] == raw
    assert record.generation_meta["draft_fields"]["facts"] == edited
    assert fake.chat_completion.await_count == 2


@pytest.mark.asyncio
async def test_semantic_rejection_does_not_publish_editorial_text(monkeypatch):
    from app.services.document_drafting import prepare_document_draft
    state = state_for("facts")
    state["fields"]["facts"] = {"status": "filled", "value": "телефон взорвался"}
    fake = SimpleNamespace(chat_completion=AsyncMock(side_effect=[
        SimpleNamespace(content='При эксплуатации телефона произошёл взрыв.', usage=TokenUsage(1, 1, 2, False)),
        SimpleNamespace(content='{"supported": {"facts": false}}', usage=TokenUsage(1, 1, 2, False))]))
    with pytest.raises(ValueError, match="смысл"):
        await prepare_document_draft(state, fake)
    assert "draft_fields" not in state
