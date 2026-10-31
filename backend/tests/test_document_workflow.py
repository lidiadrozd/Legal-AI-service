import json
from types import SimpleNamespace

import pytest

from app.models.chat import ChatSession, Message
from app.services.document_scenarios import SCENARIOS, render_scenario
from app.services.document_workflow import (
    FieldUpdate, advance_interview, apply_updates, interview_message, new_state,
    normalize_money, normalize_field, pending_fields,
)
from app.services.llm_cost import TokenUsage


def state_for(key="pretense_debt_loan"):
    state = new_state("Нужна претензия о возврате займа")
    state["scenario"] = key
    state["phase"] = "collecting"
    return state


@pytest.mark.parametrize("raw,expected", [("7 тыс руб", "7000.00"), ("70 000 рублей", "70000.00"),
    ("1,5 млн руб", "1500000.00"), ("7000.50", "7000.50"), ("около 7 тысяч", None),
    ("-100", None), ("7000 долларов", None), ("7 тысяч 500 рублей", None)])
def test_money_is_exact_or_requires_clarification(raw, expected):
    assert normalize_money(raw) == expected


def test_catalog_has_distinct_scenarios_and_honest_provenance():
    assert len(SCENARIOS) == 54  # Expanded maintained forms plus 11 legacy structures.
    assert len({s.family for s in SCENARIOS.values()}) >= 10
    for item in SCENARIOS.values():
        assert item.review_status == "draft_structure"
        assert item.source == "original_structure"
        assert len({f.key for f in item.fields}) == len(item.fields)
    assert SCENARIOS["appeal_civil"] != SCENARIOS["appeal_arbitration"]


def test_city_only_remains_incomplete_and_cannot_finish():
    state = state_for()
    updated = apply_updates(state, [FieldUpdate(key="sender_address", value="Екатеринбург",
        status="filled", evidence="Екатеринбург")], "Екатеринбург")
    assert updated["fields"]["sender_address"]["status"] == "incomplete"
    assert "Этого недостаточно" in updated["fields"]["sender_address"]["error"]
    assert state["fields"] == {}  # JSON replacement, no in-place ORM mutation
    assert "sender_address" in {f.key for f in pending_fields(updated)}


def test_no_values_can_be_invented_or_taken_from_prompt_examples():
    state = state_for()
    updated = apply_updates(state, [
        FieldUpdate(key="sender", value="Иванов Иван Иванович", status="filled", evidence="Иван"),
        FieldUpdate(key="amount", value="7000", status="filled", evidence="7000"),
        FieldUpdate(key="date", status="unknown", evidence="Иван"),
    ], "Иван")
    assert updated["fields"] == {}


def test_unknown_fields_render_as_labeled_placeholders():
    state = state_for()
    state = apply_updates(state, [FieldUpdate(key="sender_address", status="unknown", evidence="Адрес не знаю")], "Адрес не знаю")
    assert state["fields"]["sender_address"]["status"] == "unknown"
    assert "[адрес заявителя]" in render_scenario(SCENARIOS[state["scenario"]], state["fields"])


def test_corrected_amount_replaces_previous_value_and_formats():
    state = state_for()
    for value in ("7 тыс руб", "8 тыс руб"):
        state = apply_updates(state, [FieldUpdate(key="amount", status="filled", value=value, evidence=value)], value)
    assert state["fields"]["amount"]["value"] == "8000.00"
    assert "8 000 рублей" in render_scenario(SCENARIOS[state["scenario"]], state["fields"])


def test_name_capitalization_does_not_discard_user_evidence():
    state = apply_updates(state_for(), [FieldUpdate(key="recipient", status="filled",
        value="Михайлова Варвара Максимовна", evidence="михайлова варвара максимовна")],
        "михайлова варвара максимовна")
    assert state["fields"]["recipient"]["status"] == "filled"


def test_interview_asks_exactly_one_field():
    state = state_for()
    interview_message(state)
    assert state["last_questions"] == ["sender"]


@pytest.mark.asyncio
async def test_prior_form_and_turns_remain_available_and_unknown_advances(monkeypatch):
    state = state_for()
    state["request"] = "знакомый не вернул 7 тысяч рублей по расписке"
    state["last_questions"] = ["sender_address"]
    fake = FakeClient([{"updates": [], "intent": "answer", "explanation": ""}])
    async def client(): return fake
    monkeypatch.setattr("app.services.document_workflow.get_gigachat_client", client)
    updated, _, _ = await advance_interview(state, "не знаю", prior_user_turns=["Петров Иван Иванович"])
    assert updated["fields"]["sender_address"]["status"] == "unknown"
    assert "7 тысяч" in updated["request"]
    assert "Петров Иван Иванович" in updated["user_turns"]
    assert not fake.calls  # A known active field needs no provider round-trip.


def test_no_limit_on_total_questions_and_complete_only_after_all_fields():
    state = state_for()
    scenario = SCENARIOS[state["scenario"]]
    for item in scenario.fields:
        interview_message(state)
        assert state["phase"] == "collecting"
        state["fields"][item.key] = {"value": None, "status": "unknown"}
    response = interview_message(state)
    assert state["phase"] == "ready"
    assert "Все поля" in response


class FakeClient:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []

    async def chat_completion(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return SimpleNamespace(content=json.dumps(next(self.replies), ensure_ascii=False), usage=TokenUsage(1, 1, 2, False))


@pytest.mark.asyncio
async def test_help_does_not_fill_fields_and_preserves_earlier_answers(monkeypatch):
    state = state_for()
    state["fields"]["sender"] = {"status": "filled", "value": "Петров Пётр"}
    fake = FakeClient([{"intent": "help", "explanation": "Нужен полный почтовый адрес.",
        "updates": [{"key": "sender_address", "status": "unknown", "evidence": "не знаю"}]}])
    async def client(): return fake
    monkeypatch.setattr("app.services.document_workflow.get_gigachat_client", client)
    updated, answer, usage = await advance_interview(state, "Не понял вопрос: какой адрес?")
    assert "адрес" in answer.lower() and "займодав" in answer.lower()
    assert updated["fields"] == state["fields"]
    assert usage.total_tokens == 2
    # Once selected, no catalog/other templates are sent on subsequent turns.
    data = json.loads(fake.calls[0][0][1]["content"])
    assert "catalog" not in data
    assert data["scenario"]["key"] == state["scenario"]


@pytest.mark.asyncio
async def test_start_api_persists_interview_and_rejects_foreign_context(client, db_session, monkeypatch):
    fake = FakeClient([{ "updates": [], "intent": "answer", "explanation": ""}])
    async def fake_client(): return fake
    monkeypatch.setattr("app.services.document_workflow.get_gigachat_client", fake_client)
    response = await client.post("/documents/interviews", json={"prompt": "Составь претензию о возврате займа"})
    assert response.status_code == 201, response.text
    chat_id = response.json()["chat_id"]
    saved = await client.get(f"/documents/interviews/{chat_id}")
    assert saved.json()["scenario"] == "pretense_debt_loan"
    assert saved.json()["phase"] == "collecting"
    assert (await client.post(f"/documents/interviews/{chat_id}/export")).status_code == 409
    other = ChatSession(user_id=2, title="Private", document_workflow=state_for())
    db_session.add(other)
    await db_session.commit()
    assert (await client.get(f"/documents/interviews/{other.id}")).status_code == 404
    assert (await client.post("/documents/interviews", json={"prompt": "Нужна претензия к компании", "chat_id": other.id})).status_code == 404


@pytest.mark.asyncio
async def test_export_contains_placeholders_and_provenance(client, db_session, tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.DOCUMENTS_STORAGE_DIR", str(tmp_path))
    state = state_for()
    state["fields"] = {f.key: {"value": None, "status": "unknown"} for f in SCENARIOS[state["scenario"]].fields}
    state["phase"] = "ready"
    state["filename"] = "../draft.docx"
    chat = ChatSession(user_id=1, title="Draft", document_workflow=state)
    db_session.add(chat)
    await db_session.commit()
    response = await client.post(f"/documents/interviews/{chat.id}/export")
    assert response.status_code == 201, response.text
    assert response.json()["filename"] == "draft.docx"
    downloaded = await client.get(f"/documents/{response.json()['document_id']}/download")
    from io import BytesIO
    from docx import Document
    text = "\n".join(p.text for p in Document(BytesIO(downloaded.content)).paragraphs)
    assert "[основная сумма задолженности]" in text
    # Provenance belongs to metadata; the authored DOCX keeps its own layout.
    from app.services.document_template_library import load_text_package
    package=load_text_package(SCENARIOS[state['scenario']])
    assert package['review_status']=='source_checked_draft' and not package['reviewed_by']


def test_date_is_normalized_without_guessing_year():
    spec = next(f for f in SCENARIOS["pretense_debt_loan"].fields if f.key == "date")
    assert normalize_field(spec, "24 октября 2026")[0] == "2026-10-24"
    assert normalize_field(spec, "31.02.2026")[1]
    assert normalize_field(spec, "24 октября")[1]


def test_function_schema_removes_nullable_unions_without_losing_field_enums():
    from app.services.document_workflow import InterviewReply, FieldUpdate, _function_schema
    schema = InterviewReply.model_json_schema()
    schema["properties"]["updates"]["items"] = FieldUpdate.model_json_schema()
    schema.pop("$defs", None)
    converted = _function_schema(schema)
    def check(value):
        if isinstance(value, dict):
            assert "anyOf" not in value
            assert not isinstance(value.get("type"), list)
            for child in value.values(): check(child)
        elif isinstance(value, list):
            for child in value: check(child)
    check(converted)
    item = converted["properties"]["updates"]["items"]
    assert item["properties"]["value"]["type"] == "string"
    assert item["properties"]["status"]["enum"] == ["filled", "unknown", "not_applicable"]
    assert "evidence" in item["required"]
    assert "anyOf" in schema["properties"]["updates"]["items"]["properties"]["value"]


@pytest.mark.asyncio
async def test_ambiguous_unknown_does_not_skip_multiple_questions():
    state = state_for()
    state["last_questions"] = ["sender", "sender_address", "recipient"]  # legacy session
    updated, answer, usage = await advance_interview(state, "не знаю")
    assert updated == state
    assert "к какому из вопросов" in answer
    assert usage.total_tokens == 0


def test_schema_upgrade_preserves_existing_chats_and_is_idempotent():
    from sqlalchemy import create_engine, text, inspect
    from app.db.document_workflow_schema import ensure_document_workflow_column
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE chat_sessions (id INTEGER PRIMARY KEY, title TEXT)"))
        connection.execute(text("INSERT INTO chat_sessions (id, title) VALUES (1, 'Existing')"))
        ensure_document_workflow_column(connection)
        ensure_document_workflow_column(connection)
        assert "document_workflow" in {c["name"] for c in inspect(connection).get_columns("chat_sessions")}
        assert connection.execute(text("SELECT title FROM chat_sessions WHERE id=1")).scalar() == "Existing"
    engine.dispose()


def test_template_packages_reject_unknown_fields_and_pin_review_metadata(tmp_path, monkeypatch):
    from app.services import document_template_library as library
    monkeypatch.setattr(library, "TEMPLATE_ROOT", tmp_path)
    scenario = SCENARIOS["pretense_debt_loan"]
    package = {"scenario": scenario.key, "version": 2, "source": "Own reviewed text", "usage_basis": "Own authorship",
               "reviewed_by": "Reviewer", "reviewed_at": "2026-10-24", "blocks": [{"text": "Сумма: {{amount}}. Адрес: {{sender_address}}"}]}
    path = tmp_path / f"{scenario.key}.json"
    path.write_text(json.dumps(package), encoding="utf-8")
    loaded = library.load_text_package(scenario)
    assert loaded["version"] == 2
    text = render_scenario(scenario, {"amount": {"value": "7000.00", "status": "filled"}}, loaded)
    assert "7 000 рублей" in text and "[адрес заявителя]" in text
    package["blocks"][0]["text"] = "{{invented_field}}"
    path.write_text(json.dumps(package), encoding="utf-8")
    with pytest.raises(ValueError, match="Unknown template placeholder"):
        library.load_text_package(scenario)


@pytest.mark.asyncio
async def test_interview_turn_in_chat_stream_persists_json(client, db_session, monkeypatch):
    from app.api import chat as chat_api
    client._transport.app.include_router(chat_api.router)
    async def noop(*args, **kwargs): return None
    async def empty(*args, **kwargs): return []
    async def zero(*args, **kwargs): return 0
    monkeypatch.setattr(chat_api, "sync_user_interests_from_message", noop)
    monkeypatch.setattr(chat_api, "get_relevant_law_changes_for_user", empty)
    monkeypatch.setattr(chat_api, "build_rag_bundle", lambda text: ("", []))
    monkeypatch.setattr(chat_api._law_change_crud, "get_multi", empty)
    monkeypatch.setattr(chat_api._law_change_crud, "count", zero)
    monkeypatch.setattr(chat_api, "save_chat_law_references", noop)
    # Avoid artificial per-chunk delays in this transport test.
    original_sleep = chat_api.asyncio.sleep
    async def fast_sleep(delay): await original_sleep(0)
    monkeypatch.setattr(chat_api.asyncio, "sleep", fast_sleep)
    state = state_for()
    chat = ChatSession(user_id=1, title="Interview", document_workflow=state)
    db_session.add(chat)
    await db_session.commit()
    fake = FakeClient([{"intent": "answer", "explanation": "", "updates": [
        {"key": "amount", "value": "7 тыс руб", "status": "filled", "evidence": "7 тыс руб"}]}])
    async def fake_client(): return fake
    monkeypatch.setattr("app.services.document_workflow.get_gigachat_client", fake_client)
    response = await client.post(f"/chat/{chat.id}/send_stream", json={"content": "Сумма 7 тыс руб"})
    assert response.status_code == 200
    assert "[DONE]" in response.text
    assert "Ошибка" not in response.text
    await db_session.refresh(chat)
    assert chat.document_workflow["fields"]["amount"]["value"] == "7000.00"
    history = await client.get(f"/chat/{chat.id}/history")
    assert history.json()[-1]["role"] == "assistant"
    assert history.json()[-1]["content"]


def test_all_32_text_packages_are_valid_and_never_claim_lawyer_review():
    from app.services.document_template_library import load_text_package
    for scenario in SCENARIOS.values():
        package = load_text_package(scenario)
        assert package is not None, scenario.key
        assert package["review_status"] == "source_checked_draft"
        assert package["reviewed_by"] is None
        from datetime import date
        assert date.fromisoformat(package['checked_at']) <= date.today()
        assert any(block["role"] == "title" for block in package["blocks"])
        rendered = render_scenario(scenario, {}, package)
        assert "{{" not in rendered
        assert "[" in rendered


def test_template_cannot_claim_review_without_reviewer(tmp_path, monkeypatch):
    from app.services import document_template_library as library
    monkeypatch.setattr(library, "TEMPLATE_ROOT", tmp_path)
    key = "pretense_debt_loan"
    data = {"scenario": key, "version": 1, "source": "Source", "usage_basis": "Original",
            "review_status": "lawyer_reviewed", "blocks": [{"text": "{{sender}}"}]}
    (tmp_path / f"{key}.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="reviewer"):
        library.load_text_package(SCENARIOS[key])


def test_legal_docx_has_right_header_both_signatures_and_fixed_typography():
    from app.services.document_workflow_docx import build_legal_docx
    from docx import Document
    from io import BytesIO
    content = build_legal_docx("Договор", [{"role": "title", "text": "Договор"},
        {"role": "addressee", "text": "Адрес"}, {"role": "signature", "text": "Сторона 1"},
        {"role": "signature", "text": "Сторона 2"}], review_note="Проект")
    document = Document(BytesIO(content))
    assert document.paragraphs[1].paragraph_format.left_indent.cm == pytest.approx(8, abs=.01)
    assert document.paragraphs[0].style.name == "Title"
    assert document.paragraphs[0].runs[0].font.name == "Times New Roman"
    assert document.paragraphs[0].runs[0].font.size.pt == 14
    assert document.sections[0].left_margin.cm == pytest.approx(3, abs=.01)
    assert document.sections[0].different_first_page_header_footer
    assert document.sections[0].header_distance.cm == pytest.approx(1, abs=.01)
    assert "Сторона 2" in "\n".join(p.text for p in document.paragraphs)
    header_xml = document.sections[0].header.part.blob.decode("utf-8")
    footer_xml = document.sections[0].footer.part.blob.decode("utf-8")
    assert 'PAGE' in header_xml and 'fldSimple' in header_xml
    assert 'PAGE' not in footer_xml


@pytest.mark.asyncio
@pytest.mark.parametrize("output_format", ["docx", "pdf", "txt"])
async def test_sourced_package_export_formats(client, db_session, tmp_path, monkeypatch, output_format):
    # The real converter is exercised by the separate Docker PDF audit.
    monkeypatch.setattr('app.services.document_docx_template.docx_to_pdf', lambda payload: b'%PDF-1.4\nunit-converter')
    from app.services.document_template_library import load_text_package
    monkeypatch.setattr("app.core.config.settings.DOCUMENTS_STORAGE_DIR", str(tmp_path))
    state = state_for()
    scenario = SCENARIOS[state["scenario"]]
    state["fields"] = {f.key: {"value": None, "status": "unknown"} for f in scenario.fields}
    state["fields"]["amount"] = {"value": "7000.00", "status": "filled"}
    state["text_package"] = load_text_package(scenario)
    state["phase"] = "ready"
    state["output_format"] = output_format
    chat = ChatSession(user_id=1, title="Text template", document_workflow=state)
    db_session.add(chat)
    await db_session.commit()
    response = await client.post(f"/documents/interviews/{chat.id}/export")
    assert response.status_code == 201, response.text
    downloaded = await client.get(f"/documents/{response.json()['document_id']}/download")
    assert downloaded.status_code == 200
    if output_format == "docx":
        from io import BytesIO
        from docx import Document
        document = Document(BytesIO(downloaded.content))
        assert "7 000 рублей" in "\n".join(p.text for p in document.paragraphs)
        assert document.paragraphs[0].paragraph_format.left_indent.cm == pytest.approx(8, abs=.01)
    elif output_format == "pdf":
        assert downloaded.content.startswith(b"%PDF")
    else:
        assert "7 000 рублей" in downloaded.content.decode("utf-8")
