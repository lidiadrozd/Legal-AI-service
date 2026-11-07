"""Opt-in real GigaChat regression for the actual conversational failure cases."""
import asyncio
import json
import sys
from pathlib import Path

from app.services.document_workflow import advance_interview, new_state
from app.services.document_scenarios import SCENARIOS
from app.services.document_template_library import load_text_package
from app.services.document_drafting import prepare_document_draft, presentation_fields
from app.services.gigachat_client import get_gigachat_client


def sample(key):
    state = new_state("Иск о защите прав потребителей: при зарядке взорвался телефон стоимостью 66 тысяч рублей")
    state.update(scenario="claim_consumer", phase="collecting", last_questions=[key])
    state["text_package"] = load_text_package(SCENARIOS["claim_consumer"])
    state["fields"] = {"sender": {"status": "filled", "value": "Петров Иван Иванович"},
                       "amount": {"status": "filled", "value": "66000.00"},
                       "procedure": {"status": "filled", "value": "для личных нужд"}}
    return state


async def main():
    report = []
    cases = [
        ("sender_address", "кто такой истец?"),
        ("party_details", "какие например?"),
        ("seller_response", "поясни вопрос"),
        ("copy_notice", "какого документа?"),
        ("calculation", "66000 — стоимость телефона + моральный вред, сам посчитай"),
    ]
    for key, message in ([] if "--editor-only" in sys.argv else cases):
        state, answer, usage = await advance_interview(sample(key), message)
        assert state["fields"].get(key, {}).get("value") != message
        assert len(answer) > 65 and state["last_questions"] == [key]
        report.append({"field": key, "message": message, "answer": answer, "tokens": usage.total_tokens})
        print(json.dumps(report[-1], ensure_ascii=False), flush=True)
        if key == "calculation":
            state, answer, _ = await advance_interview(state, "10 тыс руб")
            assert state["fields"]["calculation"]["components"]["moral_damage"] == "10000.00"
            assert "76000.00" in state["fields"]["calculation"]["value"]
    state = sample("signature")
    scenario = SCENARIOS["claim_consumer"]
    for field in scenario.fields:
        state["fields"].setdefault(field.key, {"status": "unknown", "value": None})
    for key, value in {
        "purchase": "телефон для себя, чтобы звонить",
        "facts": "я заряжала телефон на тумбочке рядом со мной и он неожиданно взорвался",
        "violation": "телефон взорвался и чуть не поколечил меня",
        "requests": "вернуть 66000 рублей за телефон",
        "attachments": "чек о покупке телефона",
        "seller_response": "после поломки я позвонила продавцу, ответа не получила",
    }.items(): state["fields"][key] = {"status": "filled", "value": value}
    import app.services.document_workflow as workflow
    original = workflow._structured
    async def inspect_editor(*args, **kwargs):
        response = await original(*args, **kwargs)
        print("EDITOR_REPLY", response.content, flush=True)
        return response
    workflow._structured = inspect_editor
    editor_client = await get_gigachat_client()
    original_completion = editor_client.chat_completion
    async def inspect_copy(*args, **kwargs):
        response = await original_completion(*args, **kwargs)
        print("COPY", response.content, flush=True)
        return response
    editor_client.chat_completion = inspect_copy
    state = workflow.sanitize_interview(state)
    state, _ = await prepare_document_draft(state, editor_client)
    output = presentation_fields(state)
    assert output["facts"]["value"] != state["fields"]["facts"]["value"]
    assert "draft_digest" in state
    print("EDITORIAL", json.dumps(state["draft_fields"], ensure_ascii=False), flush=True)
    Path("/app/tests/live_document_conversation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    Path("/app/tests/live_document_edited_state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SUCCESS: questions answered; no question stored as fact; official editor preserved source facts", flush=True)


asyncio.run(main())
