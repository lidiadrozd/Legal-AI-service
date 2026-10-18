from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from app.db.base_class import Base
from app.core.config import settings
from app.models.chat import ChatSession, Message
from app.models.chat_law_reference import ChatLawReference, LawChangeNorm
from app.models.law_changes import LawDocument, LawChange
from app.models.law_reference_assessment import LawReferenceAssessment, LawChangeDelivery
from app.models.law_monitor_state import LawMonitorState
from app.models.user_law_interest import UserLawInterest
from app.models.notification import Notification
from app.services import law_change_monitor as monitor, law_notification_service as dispatcher
from app.services.answer_norms import extract_answer_norms, TK_KEY
from app.services.legal_sources import NormIdentity
from app.services.law_reference_service import save_chat_law_references
from app.services.law_change_parser import (ParsedLawChange, parse_consultant_periods,
    parse_consultant_period_categories, consultant_period_dates)

INDEX = "https://www.consultant.ru/law/review/fed/updprof/"
BASE = "https://www.consultant.ru/document/cons_doc_LAW_33770/"
PERIODS = [BASE + str(i)*40 + "/" for i in (1,2,3)]
CATEGORIES = [BASE + str(i)*40 + "/" for i in (4,5,6)]
LABELS = ["с 1 по 7 сентября 2026 года", "с 8 по 14 сентября 2026 года", "с 15 по 21 сентября 2026 года"]
ROOT = "https://www.consultant.ru/document/cons_doc_LAW_34683/"
PUBS = ["https://www.consultant.ru/document/cons_doc_LAW_900" + str(i) + "/" for i in range(3)]


def index_html(weeks):
    return "".join(f'<a href="{PERIODS[i]}#dst1">{LABELS[i]}</a>' for i in weeks)


def period_html(i):
    return f'<div class="document-page__toc"><ul><li><a href="{CATEGORIES[i]}">Федеральные законы, кодексы</a></li></ul></div>'


def category_html(i, *, civil=False):
    root = "https://www.consultant.ru/document/cons_doc_LAW_5142/" if civil else ROOT
    identity = "30.11.1994 N 51-ФЗ" if civil else "30.12.2001 N 197-ФЗ"
    title = "Гражданский кодекс" if civil else "Трудовой кодекс"
    return (f'<div class="document-page__content"><p>"{title}" <a href="{root}">кодекс</a> от {identity}</p>'
            f'<p>(ред. от {str(7+i*7).zfill(2)}.09.2026)</p>'
            f'<p>(изменения, внесенные Федеральным <a href="{PUBS[i]}">законом</a> от 01.09.2026 N 1-ФЗ)</p></div>')


def amendment_html(article, *, civil=False):
    root = "https://www.consultant.ru/document/cons_doc_LAW_5142/" if civil else ROOT
    return f'<div class="document-page__content"><p><a href="{root}">Статью {article}</a> изложить в новой редакции.</p></div>'


@pytest_asyncio.fixture
async def recovery_db(db_session):
    conn = await db_session.connection()
    await conn.run_sync(lambda sync: Base.metadata.create_all(sync, tables=[
        LawDocument.__table__, LawChange.__table__, UserLawInterest.__table__,
        ChatLawReference.__table__, LawChangeNorm.__table__, LawReferenceAssessment.__table__,
        LawChangeDelivery.__table__, LawMonitorState.__table__]))
    await db_session.commit()
    return db_session


def bind_monitor(monkeypatch, db, handler, tmp_path):
    @asynccontextmanager
    async def session():
        yield db
    monkeypatch.setattr(monitor, "AsyncSessionLocal", session)
    real = httpx.AsyncClient
    monkeypatch.setattr(monitor.httpx, "AsyncClient", lambda **kwargs: real(transport=httpx.MockTransport(handler),
        **{k:v for k,v in kwargs.items() if k != "transport"}))
    monkeypatch.setattr(settings, "RAG_DOCS_PATH", str(tmp_path))
    monkeypatch.setattr(settings, "LAW_CHANGE_CURATED_FILE", "")
    monkeypatch.setattr(dispatcher, "publish_notification", Mock())


async def seed_user(db, user):
    db.add(user)
    chat = ChatSession(user_id=user.id, title="Рабочий вопрос")
    db.add(chat)
    await db.flush()
    question = Message(chat_id=chat.id, role="user", content="Как защитить мои права?")
    answer = Message(chat_id=chat.id, role="assistant", content="Ответ основан на статье 10 ТК РФ.")
    db.add_all([question, answer])
    await db.flush()
    await save_chat_law_references(db, user_id=user.id, chat_id=chat.id, user_message_id=question.id,
        assistant_message_id=answer.id, references=extract_answer_norms(answer.content))
    await db.commit()
    return chat


def test_period_links_deduplicate_and_reject_other_hosts():
    html = index_html([2,1,0]) + index_html([2]) + '<a href="https://evil.example/document/cons_doc_LAW_33770/' + 'f'*40 + '/">с 1 по 2 мая 2026 года</a>'
    assert parse_consultant_periods(html, INDEX) == [(LABELS[i], PERIODS[i]) for i in (2,1,0)]


def test_period_dates_across_months_and_year():
    assert consultant_period_dates("с 28 сентября по 3 октября 2026 года") == (datetime(2026,9,28), datetime(2026,10,3))
    assert consultant_period_dates("с 29 декабря по 4 января 2026 года") == (datetime(2025,12,29),datetime(2026,1,4))
    assert consultant_period_dates("с 31 по 32 февраля 2026 года") is None


def test_toc_selects_categories_of_requested_period():
    html = '<div class="document-page__toc"><ul>' + ''.join(
        f'<li><a href="{PERIODS[i]}">{LABELS[i]}</a><ul><li><a href="{CATEGORIES[i]}">Кодексы</a></li></ul></li>' for i in (2,1,0)) + '</ul></div>'
    assert parse_consultant_period_categories(html, PERIODS[1]) == [("Кодексы", CATEGORIES[1])]
    assert parse_consultant_period_categories(html, CATEGORIES[1]) == []


@pytest.mark.asyncio
async def test_outage_then_catch_up_missed_week_and_notify_once(recovery_db, test_user, monkeypatch, tmp_path):
    db = recovery_db
    chat = await seed_user(db, test_user)
    chat_id = chat.id
    state = {"weeks":[0], "down":False}
    requests = []
    def handler(request):
        url = str(request.url); requests.append(url)
        if url == INDEX:
            if state["down"]: raise httpx.ReadTimeout("offline", request=request)
            return httpx.Response(200, text=index_html(state["weeks"]))
        if url in PERIODS: return httpx.Response(200, text=period_html(PERIODS.index(url)))
        if url in CATEGORIES:
            i = CATEGORIES.index(url); return httpx.Response(200, text=category_html(i,civil=i==2))
        if url in PUBS:
            i = PUBS.index(url); return httpx.Response(200,text=amendment_html(11 if i==0 else 10,civil=i==2))
        raise AssertionError("Unexpected URL")
    bind_monitor(monkeypatch, db, handler, tmp_path)
    assert len(await monitor.monitor_sources([INDEX])) == 1
    assert await dispatcher.dispatch_law_change_notifications(db) == 0
    checkpoint = await db.scalar(select(LawMonitorState))
    successful = checkpoint.last_success_at
    state["down"] = True
    assert await monitor.monitor_sources([INDEX]) == []
    assert checkpoint.last_success_at == successful and checkpoint.last_error == "ReadTimeout"
    state.update(down=False,weeks=[2,1,0])
    requests.clear()
    assert len(await monitor.monitor_sources([INDEX])) == 2
    assert PERIODS[1] in requests and PERIODS[0] not in requests
    assert checkpoint.last_success_at.replace(tzinfo=timezone.utc) > successful.replace(tzinfo=timezone.utc) and checkpoint.last_error is None
    assert checkpoint.progress["pending_periods"] == {}
    assert await dispatcher.dispatch_law_change_notifications(db) == 1
    delivery = await db.scalar(select(LawChangeDelivery))
    assert delivery.payload_meta["chat_id"] == chat_id
    assert await monitor.monitor_sources([INDEX]) == []
    assert await dispatcher.dispatch_law_change_notifications(db) == 0
    assert len(list(await db.scalars(select(Notification)))) == 1


@pytest.mark.asyncio
async def test_partial_period_is_retried_and_does_not_advance_success(recovery_db, monkeypatch, tmp_path):
    failed = True
    def handler(request):
        url = str(request.url)
        if url == INDEX: return httpx.Response(200,text=index_html([0]))
        if url == PERIODS[0]: return httpx.Response(200,text=period_html(0))
        if url == CATEGORIES[0]: return httpx.Response(503) if failed else httpx.Response(200,text=category_html(0))
        if url == PUBS[0]: return httpx.Response(200,text=amendment_html(11))
        raise AssertionError("Unexpected URL")
    bind_monitor(monkeypatch,recovery_db,handler,tmp_path)
    assert await monitor.monitor_sources([INDEX]) == []
    checkpoint = await recovery_db.scalar(select(LawMonitorState))
    assert checkpoint.last_success_at is None
    assert checkpoint.progress["pending_periods"] == {PERIODS[0]:LABELS[0]}
    failed = False
    assert len(await monitor.monitor_sources([INDEX])) == 1
    assert checkpoint.last_success_at and checkpoint.progress["pending_periods"] == {}


@pytest.mark.asyncio
async def test_old_pending_publication_retried_without_its_overview_and_notifies(recovery_db, test_user, monkeypatch, tmp_path):
    db = recovery_db
    await seed_user(db,test_user)
    pending = ParsedLawChange(title="Трудовой кодекс", change_date=datetime(2026,9,1), description="Поправка",
        source_url=ROOT, document_number="197-ФЗ", document_key=TK_KEY,
        amendment_source_urls=(PUBS[0],),norm_resolution_pending=True)
    change, = await monitor.persist_parsed_changes(db,[pending])
    info = dict(change.diff["norm_resolution"])
    info["next_attempt_at"] = (datetime.now(timezone.utc)-timedelta(days=1)).isoformat()
    change.diff = {**change.diff,"norm_mapping_pending":False,"norm_resolution":info}
    change.created_at = datetime.now(timezone.utc)-timedelta(days=10)
    await db.commit()
    def handler(request):
        if str(request.url)==INDEX: return httpx.Response(503)
        if str(request.url)==PUBS[0]: return httpx.Response(200,text=amendment_html(10))
        raise AssertionError("Must use saved publication URL")
    bind_monitor(monkeypatch,db,handler,tmp_path)
    assert await monitor.monitor_sources([INDEX]) == []
    assert change.diff["norm_resolution"]["state"] == "resolved"
    assert change.diff["norm_resolution"]["attempts"] == 2
    assert change.diff["norm_mapping_pending"] is True
    assert await dispatcher.dispatch_law_change_notifications(db) == 1
    assert await dispatcher.dispatch_law_change_notifications(db) == 0


@pytest.mark.asyncio
async def test_archive_gap_is_recorded_instead_of_claiming_complete_history(recovery_db, monkeypatch, tmp_path):
    db = recovery_db
    state = LawMonitorState(source_url=INDEX, progress={"coverage_through":"2026-08-01"},coverage_gap=False,
        last_success_at=datetime(2026,8,2,tzinfo=timezone.utc))
    db.add(state);await db.commit()
    def handler(request):
        url = str(request.url)
        if url==INDEX:return httpx.Response(200,text=index_html([2]))
        if url==PERIODS[2]:return httpx.Response(200,text=period_html(2))
        if url==CATEGORIES[2]:return httpx.Response(200,text=category_html(2,civil=True))
        if url==PUBS[2]:return httpx.Response(200,text=amendment_html(10,civil=True))
        raise AssertionError("Unexpected URL")
    bind_monitor(monkeypatch,db,handler,tmp_path)
    await monitor.monitor_sources([INDEX])
    assert state.last_success_at and state.coverage_gap is True


@pytest.mark.asyncio
async def test_tracked_article_snapshots_baseline_change_error_and_no_duplicates(recovery_db, test_user, monkeypatch):
    db = recovery_db
    await seed_user(db, test_user)
    monkeypatch.setattr(dispatcher, "publish_notification", Mock())
    url = "https://www.consultant.ru/document/cons_doc_LAW_34683/"
    state = {"text":"Первый текст.", "bad":False}
    def handler(request):
        assert str(request.url) == url
        if state["bad"]:
            return httpx.Response(200, text="Ошибка доступа")
        return httpx.Response(200, text='<div class="document-page__content"><p>Трудовой кодекс Российской Федерации от 30.12.2001 N 197-ФЗ (ред. от 01.10.2026)</p><p>Статья 10. Правила</p><p>'+state["text"]+'</p></div>')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        tracked = [(url, TK_KEY)]
        assert await monitor.refresh_tracked_article_snapshots(db, client, tracked) == []
        assert await dispatcher.dispatch_law_change_notifications(db) == 0
        state["text"] = "Второй текст."
        assert len(await monitor.refresh_tracked_article_snapshots(db, client, tracked)) == 1
        assert await dispatcher.dispatch_law_change_notifications(db) == 1
        assert await monitor.refresh_tracked_article_snapshots(db, client, tracked) == []
        assert await dispatcher.dispatch_law_change_notifications(db) == 0
        checkpoint = await db.scalar(select(LawMonitorState).where(LawMonitorState.source_url.like("article_snapshot:%")))
        saved = checkpoint.progress
        state["bad"] = True
        assert await monitor.refresh_tracked_article_snapshots(db, client, tracked) == []
        assert checkpoint.progress == saved
        assert checkpoint.last_error == "document_identity_unconfirmed"
        assert len(list(await db.scalars(select(Notification)))) == 1


@pytest.mark.asyncio
async def test_overview_listing_is_held_until_article_is_confirmed(recovery_db, test_user, monkeypatch):
    await seed_user(recovery_db, test_user)
    monkeypatch.setattr(dispatcher, "publish_notification", Mock())
    change = ParsedLawChange(title="Обзор редакции", source_url=ROOT, document_number="197-ФЗ",
        change_date=datetime.now(timezone.utc), description="Обзор без статьи", document_key=TK_KEY,
        affected_norms=(NormIdentity(TK_KEY),),
        norm_evidence=({"method":"overview_document_identity", "document_key":TK_KEY},),
        scope_resolution={"status":"unresolved","reason":"amendment_link_missing"})
    await monitor.persist_parsed_changes(recovery_db, [change])
    assert await dispatcher.dispatch_law_change_notifications(recovery_db) == 0
    from dataclasses import replace
    precise = replace(change, affected_norms=(NormIdentity(TK_KEY,"10"),),
        norm_evidence=({"method":"consultant_explicit_link", "document_key":TK_KEY},),
        scope_resolution={"status":"confirmed","method":"explicit_instruction"})
    await monitor.persist_parsed_changes(recovery_db, [precise])
    assert await dispatcher.dispatch_law_change_notifications(recovery_db) == 1
    assert await dispatcher.dispatch_law_change_notifications(recovery_db) == 0
