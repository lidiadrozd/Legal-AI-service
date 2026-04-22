import pytest

from app.core.config import settings
from app.models.chat import ChatSession, Message


@pytest.mark.asyncio
async def test_upload_and_list_documents(client, tmp_path):
    settings.DOCUMENTS_STORAGE_DIR = str(tmp_path)

    response = await client.post(
        "/documents/upload",
        files={"file": ("sample.txt", b"hello legal ai", "text/plain")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "ready"
    document_id = body["document_id"]

    list_resp = await client.get("/documents")
    assert list_resp.status_code == 200
    rows = list_resp.json()
    assert len(rows) >= 1
    assert any(row["id"] == document_id for row in rows)


@pytest.mark.asyncio
async def test_generate_template_document_and_download(client, tmp_path):
    settings.DOCUMENTS_STORAGE_DIR = str(tmp_path)

    payload = {
        "template_key": "statement_of_claim_arbitration",
        "filename": "claim_draft",
        "output_format": "docx",
        "fields": {
            "court_name": "Арбитражный суд г. Москвы",
            "plaintiff_name": "Иванов И.И.",
            "plaintiff_address": "г. Москва, ул. Пример, д. 1",
            "defendant_name": "ООО Ромашка",
            "defendant_address": "г. Москва, ул. Тестовая, д. 2",
            "claim_amount": "150 000 руб.",
            "facts": "Между сторонами заключен договор, обязательства не исполнены.",
            "legal_basis": "Ст. 309 и 310 ГК РФ.",
            "requests": "Взыскать задолженность и расходы по госпошлине.",
            "attachments": "Договор, акты, переписка",
            "date": "2026-04-22",
        },
    }
    create_resp = await client.post("/documents/generate", json=payload)
    assert create_resp.status_code == 201
    document_id = create_resp.json()["document_id"]

    download_resp = await client.get(f"/documents/{document_id}/download")
    assert download_resp.status_code == 200
    assert download_resp.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert download_resp.content[:2] == b"PK"


@pytest.mark.asyncio
async def test_generate_txt_template_document_and_download(client, tmp_path):
    settings.DOCUMENTS_STORAGE_DIR = str(tmp_path)
    payload = {
        "template_key": "motion_to_postpone_hearing",
        "filename": "postpone-motion",
        "output_format": "txt",
        "fields": {
            "court_name": "Арбитражный суд Московской области",
            "case_number": "А41-1000/2026",
            "applicant_name": "Петров П.П.",
            "hearing_date": "2026-05-10",
            "reasons": "Командировка представителя и необходимость представить дополнительные доказательства.",
            "new_hearing_date": "2026-05-24",
            "attachments": "Билеты, приказ о командировке",
            "date": "2026-04-22",
        },
    }
    create_resp = await client.post("/documents/generate", json=payload)
    assert create_resp.status_code == 201
    document_id = create_resp.json()["document_id"]

    download_resp = await client.get(f"/documents/{document_id}/download")
    assert download_resp.status_code == 200
    assert download_resp.headers["content-type"].startswith("text/plain")
    content = download_resp.content.decode("utf-8")
    assert "ХОДАТАЙСТВО" in content
    assert "А41-1000/2026" in content


@pytest.mark.asyncio
async def test_generate_pdf_template_document_and_download(client, tmp_path):
    settings.DOCUMENTS_STORAGE_DIR = str(tmp_path)
    payload = {
        "template_key": "appeal_complaint",
        "filename": "appeal",
        "output_format": "pdf",
        "fields": {
            "appeal_court_name": "Девятый арбитражный апелляционный суд",
            "first_instance_court_name": "Арбитражный суд г. Москвы",
            "case_number": "А40-5555/2026",
            "appellant_name": "ООО Истец",
            "challenged_act": "Решение от 01.04.2026",
            "grounds": "Неправильное применение норм материального права.",
            "requests": "Отменить решение суда первой инстанции.",
            "attachments": "Копия решения, квитанция госпошлины",
            "date": "2026-04-22",
        },
    }
    create_resp = await client.post("/documents/generate", json=payload)
    assert create_resp.status_code == 201
    document_id = create_resp.json()["document_id"]

    download_resp = await client.get(f"/documents/{document_id}/download")
    assert download_resp.status_code == 200
    assert download_resp.headers["content-type"].startswith("application/pdf")
    assert download_resp.content.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_generate_template_requires_fields(client, tmp_path):
    settings.DOCUMENTS_STORAGE_DIR = str(tmp_path)
    payload = {
        "template_key": "statement_of_claim_arbitration",
        "filename": "broken",
        "fields": {
            "court_name": "Арбитражный суд г. Москвы",
        },
    }
    response = await client.post("/documents/generate", json=payload)
    assert response.status_code == 422
    assert "Missing required fields" in response.json()["detail"]


@pytest.mark.asyncio
async def test_generate_template_validates_field_format(client, tmp_path):
    settings.DOCUMENTS_STORAGE_DIR = str(tmp_path)
    payload = {
        "template_key": "motion_to_postpone_hearing",
        "filename": "bad-motion",
        "output_format": "txt",
        "fields": {
            "court_name": "Арбитражный суд Московской области",
            "case_number": "INVALID-CASE",
            "applicant_name": "Петров П.П.",
            "hearing_date": "2026-05-10",
            "reasons": "Уважительные причины",
            "new_hearing_date": "2026-05-24",
            "attachments": "Билеты",
            "date": "2026-04-22",
        },
    }
    response = await client.post("/documents/generate", json=payload)
    assert response.status_code == 422
    assert "invalid format" in response.json()["detail"]


@pytest.mark.asyncio
async def test_list_templates(client):
    response = await client.get("/documents/templates")
    assert response.status_code == 200
    rows = response.json()
    keys = {row["key"] for row in rows}
    assert "statement_of_claim_arbitration" in keys
    assert "motion_to_postpone_hearing" in keys
    assert "appeal_complaint" in keys
    assert all(row.get("version") == 1 for row in rows)
    assert any(field.get("pattern") for row in rows for field in row["fields"])


@pytest.mark.asyncio
async def test_suggest_fields_from_chat(client, db_session):
    chat = ChatSession(user_id=1, title="test")
    db_session.add(chat)
    await db_session.flush()
    db_session.add(
        Message(
            chat_id=chat.id,
            role="user",
            content="Номер дела А41-12345/2026, Арбитражный суд Московской области",
        )
    )
    await db_session.commit()

    resp = await client.post(
        "/documents/suggest-fields",
        json={"template_key": "motion_to_postpone_hearing", "chat_id": chat.id},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["template_version"] == 1
    assert body["suggested"]["case_number"] == "А41-12345/2026"
    assert body["sources"]["case_number"] == "chat_text"


@pytest.mark.asyncio
async def test_generate_with_chat_id_fills_case_number(client, db_session, tmp_path):
    settings.DOCUMENTS_STORAGE_DIR = str(tmp_path)
    chat = ChatSession(user_id=1, title="t")
    db_session.add(chat)
    await db_session.flush()
    db_session.add(Message(chat_id=chat.id, role="user", content="По делу А41-77777/2026"))
    await db_session.commit()

    payload = {
        "template_key": "motion_to_postpone_hearing",
        "filename": "motion",
        "output_format": "txt",
        "chat_id": chat.id,
        "template_version": 1,
        "fields": {
            "court_name": "Арбитражный суд Московской области",
            "case_number": "",
            "applicant_name": "Петров П.П.",
            "hearing_date": "2026-05-10",
            "reasons": "Уважительные причины",
            "new_hearing_date": "2026-05-24",
            "attachments": "Билеты",
            "date": "2026-04-22",
        },
    }
    create_resp = await client.post("/documents/generate", json=payload)
    assert create_resp.status_code == 201
    document_id = create_resp.json()["document_id"]

    meta_resp = await client.get(f"/documents/{document_id}")
    assert meta_resp.status_code == 200
    meta = meta_resp.json()["generation_meta"]
    assert meta["template_version"] == 1
    assert meta["field_sources"].get("case_number") == "chat_text"

    download_resp = await client.get(f"/documents/{document_id}/download")
    assert download_resp.status_code == 200
    assert "А41-77777/2026" in download_resp.content.decode("utf-8")


@pytest.mark.asyncio
async def test_generate_rejects_wrong_template_version(client, tmp_path):
    settings.DOCUMENTS_STORAGE_DIR = str(tmp_path)
    payload = {
        "template_key": "statement_of_claim_arbitration",
        "filename": "claim",
        "output_format": "txt",
        "template_version": 999,
        "fields": {
            "court_name": "Арбитражный суд г. Москвы",
            "plaintiff_name": "Иванов И.И.",
            "plaintiff_address": "г. Москва, ул. Пример, д. 1",
            "defendant_name": "ООО Ромашка",
            "defendant_address": "г. Москва, ул. Тестовая, д. 2",
            "claim_amount": "150 000 руб.",
            "facts": "Факты",
            "legal_basis": "Ст. 309 ГК РФ.",
            "requests": "Взыскать.",
            "attachments": "Договор",
            "date": "2026-04-22",
        },
    }
    response = await client.post("/documents/generate", json=payload)
    assert response.status_code == 422
    assert "version mismatch" in response.json()["detail"]
