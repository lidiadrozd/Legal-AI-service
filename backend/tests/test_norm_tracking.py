import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import httpx
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

from app.core.config import settings
from app.db.base_class import Base
from app.models.chat import ChatSession, Message
from app.models.law_monitor_state import LawMonitorState
from app.models.chat_law_reference import ChatLawReference, LawChangeNorm
from app.models.law_changes import LawChange, LawDocument
from app.models.law_reference_assessment import LawReferenceAssessment, LawChangeDelivery
from app.models.notification import Notification
from app.models.user_law_interest import UserLawInterest
from app.services import rag_context, nlp_service
from app.services.legal_sources import NormIdentity, load_legal_source_catalog, cited_legal_sources
from app.services.law_reference_service import save_chat_law_references, save_change_norms, find_references_for_change
from app.services.law_change_parser import parse_json_changes
from app.services.law_change_monitor import persist_parsed_changes
from app.services.llm_cost import TokenUsage
from app.services.response_cache import build_cache_key

SAMPLE = Path(__file__).resolve().parents[2] / "docs/fixtures/legal_norm_tracking"


@pytest.fixture
def rag_bundle(monkeypatch, tmp_path):
    for name in ("article_7.txt", "legal_sources.json"):
        (tmp_path / name).write_bytes((SAMPLE / name).read_bytes())
    monkeypatch.setattr(settings, "RAG_DOCS_PATH", str(tmp_path))
    monkeypatch.setattr(settings, "RAG_ENABLED", True)
    monkeypatch.setattr(settings, "RAG_RERANK_THRESHOLD", 0)
    monkeypatch.setattr(rag_context, "_INDEX", None)
    return rag_context.build_rag_bundle("обращение за учебной услугой")


@pytest_asyncio.fixture
async def norm_db(db_session):
    conn = await db_session.connection()
    await conn.execute(text("PRAGMA foreign_keys=ON"))
    # Notification.template_id is NULL in this flow. The template model uses
    # PostgreSQL ARRAY fields; this SQLite scaffold supplies only the FK target.
    await conn.execute(text("CREATE TABLE notification_templates (id INTEGER PRIMARY KEY)"))
    await conn.run_sync(lambda sync: Base.metadata.create_all(sync, tables=[
        LawDocument.__table__, LawChange.__table__, UserLawInterest.__table__,
        ChatLawReference.__table__, LawChangeNorm.__table__,
        LawReferenceAssessment.__table__, LawChangeDelivery.__table__, LawMonitorState.__table__]))
    await db_session.commit()
    return db_session


def test_catalog_rejects_changed_file_and_escaping_path(tmp_path):
    for name in ("article_7.txt", "legal_sources.json"):
        (tmp_path / name).write_bytes((SAMPLE / name).read_bytes())
    assert len(load_legal_source_catalog(tmp_path)) == 1
    (tmp_path / "article_7.txt").write_text("changed", encoding="utf-8")
    assert load_legal_source_catalog(tmp_path) == {}
    manifest = json.loads((SAMPLE / "legal_sources.json").read_text(encoding="utf-8"))
    manifest["sources"][0]["file"] = "../outside.txt"
    (tmp_path / "legal_sources.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert load_legal_source_catalog(tmp_path) == {}


def test_only_cited_offered_sources_are_tracked(rag_bundle):
    rendered, sources = rag_bundle
    assert "[Источник 1]" in rendered
    assert sources[0]["legal_source"].norm.article == "7"
    assert cited_legal_sources("Статья 7", sources) == ()
    assert cited_legal_sources("[Источник 99]", sources) == ()
    assert len(cited_legal_sources("[Источник 1] [Источник 1]", sources)) == 1
    assert cited_legal_sources("[Источник 2]", sources + [{"citation_id": 2}]) == ()


def test_cache_key_includes_norm_identity_even_if_text_is_same(rag_bundle):
    rendered, sources = rag_bundle
    other = [{**sources[0], "legal_source": replace(sources[0]["legal_source"],
              norm=replace(sources[0]["legal_source"].norm, article="8"))}]
    kwargs = {"user_query": "вопрос", "chat_history": ""}
    assert build_cache_key(context={"rag": rendered, "rag_sources": sources}, **kwargs) != build_cache_key(
        context={"rag": rendered, "rag_sources": other}, **kwargs)


@pytest.mark.asyncio
async def test_sources_survive_cached_nlp_answer(monkeypatch, rag_bundle):
    rendered, sources = rag_bundle
    completion = SimpleNamespace(content="Учебный срок: пять дней [Источник 1].", usage=TokenUsage(10, 10, 20, False))
    client = SimpleNamespace(chat_completion=AsyncMock(return_value=completion))
    monkeypatch.setattr(nlp_service, "get_gigachat_client", AsyncMock(return_value=client))
    cache_get = AsyncMock(return_value=None)
    monkeypatch.setattr(nlp_service.response_cache, "get", cache_get)
    monkeypatch.setattr(nlp_service.response_cache, "set", AsyncMock())
    service = nlp_service.NLPService()
    context = {"rag": rendered, "rag_sources": sources}
    first = await service.generate_response("Учебная услуга", context=context)
    cache_get.return_value = first.text
    second = await service.generate_response("Учебная услуга", context=context)
    assert first.references == second.references
    assert len(second.references) == 1 and second.cached
    assert client.chat_completion.call_count == 1


async def seed_reference(db, sources, *, owner=1):
    chat = ChatSession(user_id=owner, title="Учебный чат")
    db.add(chat)
    await db.flush()
    user = Message(chat_id=chat.id, role="user", content="Я обратился за учебной услугой")
    assistant = Message(chat_id=chat.id, role="assistant", content="Ответ [Источник 1]")
    db.add_all([user, assistant])
    await db.flush()
    await save_chat_law_references(db, user_id=owner, chat_id=chat.id,
        user_message_id=user.id, assistant_message_id=assistant.id, references=sources)
    return chat, user, assistant


@pytest.mark.asyncio
async def test_ownership_deduplication_and_delete(norm_db, rag_bundle):
    db = norm_db
    _, sources = rag_bundle
    chat, user, assistant = await seed_reference(db, sources)
    with pytest.raises(ValueError):
        await save_chat_law_references(db, user_id=2, chat_id=chat.id,
            user_message_id=user.id, assistant_message_id=assistant.id, references=sources)
    assert await save_chat_law_references(db, user_id=1, chat_id=chat.id,
        user_message_id=user.id, assistant_message_id=assistant.id, references=sources) == 0
    assert len(list(await db.scalars(select(ChatLawReference)))) == 1
    await db.delete(chat)
    await db.flush()
    assert list(await db.scalars(select(ChatLawReference))) == []


@pytest.mark.asyncio
async def test_precise_scope_and_user_filter(norm_db, rag_bundle):
    db = norm_db
    _, sources = rag_bundle
    own, _, _ = await seed_reference(db, sources, owner=1)
    await seed_reference(db, sources, owner=2)
    document = LawDocument(number="AMENDING", title="Учебный акт о поправках")
    db.add(document)
    await db.flush()
    for index, norm in enumerate([
        NormIdentity("training:service-rules", "8"),
        NormIdentity("different-law", "7", "1"),
        NormIdentity("training:service-rules", "7", "2"),
        NormIdentity("training:service-rules", "7"),
        NormIdentity("training:service-rules"),
    ], start=1):
        change = LawChange(id=index, document_id=document.id, description="Учебные поправки")
        db.add(change)
        await db.flush()
        await save_change_norms(db, change_id=index, norms=[norm, norm])
        found = await find_references_for_change(db, change_id=index, user_id=1)
        assert len(found) == (1 if index >= 4 else 0)
        if found:
            assert found[0].chat_id == own.id
    assert len(await find_references_for_change(db, change_id=4)) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("tracking_failure", [False, True])
@pytest.mark.parametrize("source_kind", ["local", "consultant"])
async def test_chat_answer_to_changed_article_end_to_end(norm_db, test_user, monkeypatch, rag_bundle, tracking_failure, source_kind):
    from app.api import chat as chat_api
    from app.api.notifications import router as notifications_router
    from app.services import law_notification_service as dispatcher
    from app.api.deps import get_current_user
    from app.db.session import get_db
    db = norm_db
    db.add(test_user)
    chat = ChatSession(user_id=test_user.id, title="Учебный чат")
    db.add(chat)
    await db.commit()
    fake = SimpleNamespace(chat_completion=AsyncMock(return_value=SimpleNamespace(
        content="Учебный срок — пять дней [Источник 1].", usage=TokenUsage(10, 10, 20, False))))
    monkeypatch.setattr(nlp_service, "get_gigachat_client", AsyncMock(return_value=fake))
    monkeypatch.setattr(nlp_service.response_cache, "get", AsyncMock(return_value=None))
    monkeypatch.setattr(nlp_service.response_cache, "set", AsyncMock())
    if tracking_failure:
        original_save = chat_api.save_chat_law_references
        async def fail_after_insert(*args, **kwargs):
            await original_save(*args, **kwargs)
            raise RuntimeError("storage failed")
        monkeypatch.setattr(chat_api, "save_chat_law_references", fail_after_insert)
    app = FastAPI()
    app.include_router(chat_api.router)
    app.include_router(notifications_router)
    async def get_test_db():
        yield db
    async def current_user():
        return test_user
    app.dependency_overrides[get_db] = get_test_db
    app.dependency_overrides[get_current_user] = current_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"/chat/{chat.id}/send_stream", json={"content": "Обращение за учебной услугой"})
    assert response.status_code == 200 and "[DONE]" in response.text
    references = list(await db.scalars(select(ChatLawReference)))
    if tracking_failure:
        assert references == []
        assistant = await db.scalar(select(Message).where(Message.role == "assistant"))
        assert "storage failed" in assistant.content
        return
    assert len(references) == 1
    assert references[0].source_revision == "training-v1"
    assert references[0].situation_excerpt == "Обращение за учебной услугой"
    from contextlib import asynccontextmanager
    from app.services import law_change_monitor as monitor
    @asynccontextmanager
    async def local_session():
        yield db
    monkeypatch.setattr(monitor, "AsyncSessionLocal", local_session)
    if source_kind == "local":
        monkeypatch.setattr(settings, "LAW_CHANGE_CURATED_FILE", str(SAMPLE / "curated_changes.json"))
        no_network = AsyncMock(side_effect=AssertionError("Local source must not fetch remote sources"))
        monkeypatch.setattr(monitor, "_fetch_text", no_network)
        urls = []
    else:
        root = Path(settings.RAG_DOCS_PATH)
        manifest = json.loads((root / "legal_sources.json").read_text(encoding="utf-8"))
        manifest["sources"][0]["source_url"] = "https://www.consultant.ru/document/cons_doc_LAW_500/"
        (root / "legal_sources.json").write_text(json.dumps(manifest), encoding="utf-8")
        monkeypatch.setattr(settings, "LAW_CHANGE_CURATED_FILE", "")
        category_url = "https://www.consultant.ru/document/cons_doc_LAW_33770/" + "a" * 40 + "/"
        page = ('<div class="document-page__content">'
            '<p>Федеральный <a href="/document/cons_doc_LAW_500/">закон</a> от 01.01.2020 N 100-ФЗ</p>'
            '<p>(ред. от 11.10.2026)</p><p>"Учебный закон"</p>'
            '<p>(изменения, внесенные Федеральным <a href="/document/cons_doc_LAW_600/">законом</a> '
            'от 11.10.2026 N 200-ФЗ)</p></div>')
        amendment = ('<div class="document-page__content"><p>'
            '<a href="/document/cons_doc_LAW_500/">Часть 1 статьи 7</a> '
            'учебного закона дополнить новым правилом.</p></div>')
        def handler(request):
            return httpx.Response(200, text=page if str(request.url) == category_url else amendment)
        def mock_source_client(**kwargs):
            kwargs.pop("transport", None)
            return AsyncClient(transport=httpx.MockTransport(handler), **kwargs)
        monkeypatch.setattr(monitor.httpx, "AsyncClient", mock_source_client)
        urls = [category_url]
    changes = await monitor.monitor_sources(source_urls=urls)
    assert await monitor.monitor_sources(source_urls=urls) == []
    if source_kind == "local":
        no_network.assert_not_called()
    else:
        assert changes[0].diff["norm_evidence"][0]["target_label"] == "Часть 1 статьи 7"
    found = await find_references_for_change(db, change_id=changes[0].id, user_id=test_user.id)
    assert [row.id for row in found] == [references[0].id]
    # The document containing amendments is not used as the amended document's identity.
    expected_number = "TRAINING-AMENDING-1" if source_kind == "local" else "100-ФЗ"
    assert (await db.get(LawDocument, changes[0].document_id)).number == expected_number
    assert found[0].document_key == "training:service-rules"
    publisher = Mock()
    monkeypatch.setattr(dispatcher, "publish_notification", publisher)
    assert await dispatcher.dispatch_law_change_notifications(db) == 1
    fake.chat_completion.assert_awaited_once()  # Only the original chat answer used GigaChat.
    note = await db.scalar(select(Notification))
    assert "Возможно, стоит пересмотреть прежний ответ" in note.message
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/notifications")
    assert response.status_code == 200
    assert response.json()[0]["meta"]["chat_id"] == chat.id
    assert response.json()[0]["meta"]["notification_basis"] == "article_change"
    assert await dispatcher.dispatch_law_change_notifications(db) == 0
    publisher.assert_called_once()


def test_parser_does_not_guess_affected_norm_from_act_number():
    payload = {"changes": [{"title": "Поправки", "document_number": "123-ФЗ",
                           "affected_norms": [{"article": "7"}]}]}
    assert parse_json_changes(payload, "https://example.org/changes")[0].affected_norms == ()


def test_initial_real_catalog_retrieval(monkeypatch):
    root = Path(__file__).resolve().parents[1] / "rag_docs"
    catalog = load_legal_source_catalog(root)
    assert len(catalog) == 3
    assert {source.norm.part for source in catalog.values()} == {"14", "15", "16"}
    monkeypatch.setattr(settings, "RAG_DOCS_PATH", str(root))
    monkeypatch.setattr(settings, "RAG_ENABLED", True)
    monkeypatch.setattr(settings, "RAG_RERANK_THRESHOLD", 0.2)
    monkeypatch.setattr(rag_context, "_INDEX", None)
    _, sources = rag_context.build_rag_bundle(
        "Какие операции могут осуществляться по специальному банковскому счету платежного агента?"
    )
    assert sources
    assert sources[0]["legal_source"].norm == NormIdentity("ru:103-fz:2009-06-03", "4", "16")
    assert not rag_context.build_rag_bundle("Как оформить развод и разделить квартиру супругов?")[1]


@pytest.mark.asyncio
async def test_direct_answer_citations_saved_and_matched_without_catalog(norm_db):
    from app.services.answer_norms import extract_answer_norms, TK_KEY, GK_KEY
    db = norm_db
    chat = ChatSession(user_id=1, title="Без каталога")
    db.add(chat)
    await db.flush()
    question = Message(chat_id=chat.id, role="user", content="Что делать?")
    answer = Message(chat_id=chat.id, role="assistant", content="Опирайтесь на статью 10 ТК РФ и статью 10 ГК РФ.")
    db.add_all([question, answer])
    await db.flush()
    refs = extract_answer_norms(answer.content)
    assert await save_chat_law_references(db, user_id=1, chat_id=chat.id,
        user_message_id=question.id, assistant_message_id=answer.id, references=refs) == 2
    document = LawDocument(number="TEST", title="Поправки")
    db.add(document)
    await db.flush()
    change = LawChange(document_id=document.id, change_title="Поправка")
    db.add(change)
    await db.flush()
    await save_change_norms(db, change_id=change.id, norms=[NormIdentity(TK_KEY, "10")])
    matched = await find_references_for_change(db, change_id=change.id)
    assert len(matched) == 1 and matched[0].document_key == TK_KEY
    assert matched[0].document_key != GK_KEY
    # Ignore forged URL and text: reconstruct evidence from the persisted answer.
    refs[0]["text"] = "forged"
    await save_chat_law_references(db, user_id=1, chat_id=chat.id,
        user_message_id=question.id, assistant_message_id=answer.id, references=refs)
    assert matched[0].source_text != "forged"


@pytest.mark.asyncio
async def test_document_mapping_upgrades_to_article_and_never_broadens_on_timeout(norm_db):
    from datetime import datetime, timezone
    from app.services.law_change_parser import ParsedLawChange
    key = "ru:103-fz:2009-06-03"
    broad = ParsedLawChange(title="Поправка", change_date=datetime.now(timezone.utc),
        description="Изменение закона", source_url="https://example.org/change", document_number="103-ФЗ",
        affected_norms=(NormIdentity(key),), norm_evidence=({"method":"overview_document_identity", "document_key":key},))
    created = await persist_parsed_changes(norm_db, [broad])
    precise = replace(broad, affected_norms=(NormIdentity(key, "4", "16"),),
        norm_evidence=({"method":"consultant_explicit_link"},))
    assert await persist_parsed_changes(norm_db, [precise]) == []
    assert await persist_parsed_changes(norm_db, [broad]) == []
    scopes = list(await norm_db.scalars(select(LawChangeNorm).where(LawChangeNorm.change_id == created[0].id)))
    assert len(scopes) == 1 and scopes[0].article == "4" and scopes[0].part == "16"


@pytest.mark.asyncio
@pytest.mark.parametrize("query,answer,key", [
    ("Работаю по трудовому договору. Начальник требует написать заявление. Как защититься?", "Ваши права: статья 80 ТК РФ.", "ru:197-fz:2001-12-30"),
    ("Снимаю квартиру по договору. Какие у меня права?", "Опирайтесь на статью 687 ГК РФ.", "ru:14-fz:1996-01-26"),
    ("Магазин не принимает неисправный чайник. Что делать?", "Статья 18 Закона РФ «О защите прав потребителей».", "ru:2300-1:1992-02-07"),
])
async def test_ordinary_nlp_answer_keeps_citations_without_rag(monkeypatch, query, answer, key):
    client = SimpleNamespace(chat_completion=AsyncMock(return_value=SimpleNamespace(
        content=answer, usage=TokenUsage(10, 10, 20, False))))
    monkeypatch.setattr(nlp_service, "get_gigachat_client", AsyncMock(return_value=client))
    monkeypatch.setattr(nlp_service.response_cache, "get", AsyncMock(return_value=None))
    monkeypatch.setattr(nlp_service.response_cache, "set", AsyncMock())
    result = await nlp_service.NLPService().generate_response(query, context={})
    assert answer in result.text
    assert "Не удалось оформить документ" not in result.text
    assert len(result.references) == 1
    assert result.references[0]["legal_source"].norm.document_key == key


@pytest.mark.asyncio
async def test_unresolved_refresh_cannot_disable_previously_precise_change(norm_db):
    from datetime import datetime, timezone
    from app.services.law_change_parser import ParsedLawChange
    from dataclasses import replace
    db = norm_db
    original = ParsedLawChange(title="Точная поправка", change_date=datetime.now(timezone.utc),
        source_url="https://www.consultant.ru/document/cons_doc_LAW_900/", description="Точная норма",
        affected_norms=(NormIdentity("training:law","7"),),
        norm_evidence=({"method":"consultant_explicit_link"},))
    created, = await persist_parsed_changes(db, [original])
    fallback = replace(original, affected_norms=(NormIdentity("training:law"),),
        norm_evidence=({"method":"overview_document_identity","document_key":"training:law"},),
        scope_resolution={"status":"unresolved","reason":"amendment_unresolved"})
    await persist_parsed_changes(db, [fallback])
    assert created.diff.get("scope_resolution", {}).get("status") != "unresolved"
    assert created.diff["norm_evidence"][0]["method"] == "consultant_explicit_link"
