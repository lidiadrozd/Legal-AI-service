import json
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio
from sqlalchemy import select, event

from app.db.base_class import Base
from app.models.chat import ChatSession, Message
from app.models.chat_law_reference import ChatLawReference, LawChangeNorm
from app.models.law_reference_assessment import LawReferenceAssessment, LawChangeDelivery
from app.models.law_changes import LawDocument, LawChange
from app.models.notification import Notification
from app.models.user import User
from app.models.user_law_interest import UserLawInterest
from app.services import law_notification_service as dispatcher, law_relevance_service as relevance
from app.services.law_user_context import load_reference_user_context
from app.services.law_reference_service import save_change_norms
from app.services.legal_sources import NormIdentity


@pytest_asyncio.fixture
async def db(db_session):
    conn = await db_session.connection()
    await conn.run_sync(lambda sync: Base.metadata.create_all(sync, tables=[
        LawDocument.__table__, LawChange.__table__, UserLawInterest.__table__,
        ChatLawReference.__table__, LawChangeNorm.__table__, LawReferenceAssessment.__table__,
        LawChangeDelivery.__table__]))
    await db_session.commit()
    # Model PostgreSQL outer transactions even before the first write, so
    # releasing a SAVEPOINT cannot commit a notification independently.
    event.listen(db_session.bind.sync_engine, "begin", lambda conn: conn.exec_driver_sql("BEGIN"))
    return db_session


async def seed(db, test_user, *, statements=("Я не ИП", "Я ИП"), scope=True):
    db.add(test_user)
    document = LawDocument(title="Учебный акт о поправках", number="AMENDING-1")
    db.add(document)
    await db.flush()
    change = LawChange(document_id=document.id, change_title="Учебное изменение статьи",
                       description="Новое требование для ИП.", created_at=datetime.now(timezone.utc))
    db.add(change)
    await db.flush()
    if scope:
        await save_change_norms(db, change_id=change.id, norms=[NormIdentity("training:law", "7", "1")])
    references = []
    for statement in statements:
        chat = ChatSession(user_id=test_user.id, title="Учебная ситуация")
        db.add(chat)
        await db.flush()
        user = Message(chat_id=chat.id, role="user", content=statement)
        assistant = Message(chat_id=chat.id, role="assistant", content="Я ИП. Учебный ответ [Источник 1]")
        db.add_all([user, assistant])
        await db.flush()
        reference = ChatLawReference(chat_id=chat.id, user_message_id=user.id,
            assistant_message_id=assistant.id, document_key="training:law", article="7", part="1", point="",
            source_url="https://example.org/training/law", source_revision="v1", source_sha256="0" * 64,
            source_text="ИП обязаны соблюдать учебное правило.", situation_excerpt=statement)
        db.add(reference)
        references.append(reference)
    await db.commit()
    return change, references


def fake_client(monkeypatch, verdicts):
    def response(messages, **kwargs):
        payload = json.loads(messages[1]["content"])
        if "user_statements" not in payload:
            data = {"sufficient": True, "summary": "Новое требование", "groups": [{"id": "g1", "conditions": [
                {"id": "c1", "kind": "role", "requirement": "Действующий ИП", "source_quote": "ИП"}]}]}
        else:
            verdict, evidence = next(verdicts)
            data = {"assessments": [{"id": "c1", "verdict": verdict,
                                     "fact": "Учебная проверка статуса", "evidence": evidence}]}
        return SimpleNamespace(content=json.dumps(data, ensure_ascii=False))
    client = SimpleNamespace(chat_completion=AsyncMock(side_effect=response))
    monkeypatch.setattr(relevance, "get_gigachat_client", AsyncMock(return_value=client))
    publisher = Mock()
    monkeypatch.setattr(dispatcher, "publish_notification", publisher)
    return client, publisher


@pytest.mark.asyncio
async def test_all_situations_checked_without_interests_and_only_one_notification(db, test_user, monkeypatch):
    change, refs = await seed(db, test_user)
    client, publisher = fake_client(monkeypatch, iter([("not_met", "Я не ИП"), ("met", "Я ИП")]))
    publisher.side_effect = lambda *args, **kwargs: assert_committed(db)
    assert await dispatcher.dispatch_law_change_notifications(db, check_personal_relevance=True) == 1
    assert client.chat_completion.call_count == 3  # one shared law analysis, two user matches
    assert list(await db.scalars(select(LawReferenceAssessment.status).order_by(LawReferenceAssessment.reference_id))) == [
        "irrelevant", "relevant"]
    notes = list(await db.scalars(select(Notification)))
    assert len(notes) == 1 and "Почему это касается" in notes[0].message
    delivery = await db.scalar(select(LawChangeDelivery))
    assert delivery.payload_meta["reference_ids"] == [refs[1].id]
    assert delivery.payload_meta["chat_id"] == refs[1].chat_id
    assert publisher.call_args.kwargs["user_id"] == test_user.id
    law_payload = json.loads(client.chat_completion.call_args_list[0].kwargs["messages"][1]["content"])
    assert "user_statements" not in law_payload and "prior_legal_basis" not in law_payload
    user_payload = json.loads(client.chat_completion.call_args_list[1].kwargs["messages"][1]["content"])
    assert user_payload["prior_legal_basis"]["article"] == "7"
    assert "Я ИП" not in user_payload["user_statements"]
    assert await dispatcher.dispatch_law_change_notifications(db, check_personal_relevance=True) == 0
    assert client.chat_completion.call_count == 3 and publisher.call_count == 1


def assert_committed(db):
    assert not db.in_transaction()


@pytest.mark.asyncio
async def test_pending_data_is_saved_and_rechecked_after_new_statements(db, test_user, monkeypatch):
    change, refs = await seed(db, test_user, statements=("Меня интересует ИП",))
    client, publisher = fake_client(monkeypatch, iter([("unknown", ""), ("met", "Теперь я ИП")]))
    assert await dispatcher.dispatch_law_change_notifications(db, check_personal_relevance=True) == 0
    assert await db.scalar(select(LawReferenceAssessment.status)) == "insufficient_data"
    assert await dispatcher.dispatch_law_change_notifications(db, check_personal_relevance=True) == 0
    assert client.chat_completion.call_count == 2
    change.created_at = datetime.now(timezone.utc) - timedelta(days=10)
    db.add(Message(chat_id=refs[0].chat_id, role="user", content="Теперь я ИП"))
    await db.commit()
    assert await dispatcher.dispatch_law_change_notifications(db, check_personal_relevance=True) == 1
    assert client.chat_completion.call_count == 4
    assert await db.scalar(select(LawReferenceAssessment.status)) == "relevant"
    publisher.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["irrelevant", "insufficient_data", "error"])
async def test_no_notification_for_unconfirmed_or_inconsistent_results(db, test_user, monkeypatch, status):
    await seed(db, test_user, statements=("Я ИП",))
    result = relevance.LawRelevanceResult(status == "error", "Учебное решение", status)
    mocked = AsyncMock(return_value=result)
    monkeypatch.setattr(dispatcher, "assess_law_reference_relevance", mocked)
    publisher = Mock()
    monkeypatch.setattr(dispatcher, "publish_notification", publisher)
    assert await dispatcher.dispatch_law_change_notifications(db, check_personal_relevance=True) == 0
    assert list(await db.scalars(select(Notification))) == []
    saved = await db.scalar(select(LawReferenceAssessment))
    assert saved.status == status
    if status == "error":
        assert saved.error_code == "Inconsistent relevance result"
    publisher.assert_not_called()


@pytest.mark.asyncio
async def test_api_error_is_saved_and_retried_without_notification(db, test_user, monkeypatch):
    await seed(db, test_user, statements=("Я ИП",))
    monkeypatch.setattr(relevance, "get_gigachat_client", AsyncMock(side_effect=relevance.GigaChatAPIError(402)))
    publisher = Mock()
    monkeypatch.setattr(dispatcher, "publish_notification", publisher)
    assert await dispatcher.dispatch_law_change_notifications(db, check_personal_relevance=True) == 0
    assert await db.scalar(select(LawReferenceAssessment.error_code)) == "HTTP 402"
    client, publisher = fake_client(monkeypatch, iter([("met", "Я ИП")]))
    assert await dispatcher.dispatch_law_change_notifications(db, check_personal_relevance=True) == 1
    assert await db.scalar(select(LawReferenceAssessment.status)) == "relevant"


@pytest.mark.asyncio
async def test_no_keyword_fallback_for_unmapped_change(db, test_user, monkeypatch):
    await seed(db, test_user, statements=("Я ИП",), scope=False)
    db.add(UserLawInterest(user_id=test_user.id, topic_key="ip", topic_label="ИП", keywords=["ИП"], source_excerpt="Я ИП"))
    await db.commit()
    mocked = AsyncMock()
    monkeypatch.setattr(dispatcher, "assess_law_reference_relevance", mocked)
    monkeypatch.setattr(dispatcher, "assess_law_change_relevance", mocked)
    assert await dispatcher.dispatch_law_change_notifications(db, check_personal_relevance=True) == 0
    mocked.assert_not_called()


@pytest.mark.asyncio
async def test_failed_commit_never_publishes(db, test_user, monkeypatch):
    await seed(db, test_user, statements=("Я ИП",))
    client, publisher = fake_client(monkeypatch, iter([("met", "Я ИП")]))
    monkeypatch.setattr(db, "commit", AsyncMock(side_effect=RuntimeError("commit failed")))
    with pytest.raises(RuntimeError, match="commit failed"):
        await dispatcher.dispatch_law_change_notifications(db, check_personal_relevance=True)
    publisher.assert_not_called()
    await db.rollback()
    assert list(await db.scalars(select(Notification))) == []


@pytest.mark.asyncio
async def test_reference_context_keeps_anchor_and_latest_correction_but_not_assistant(db, test_user):
    change, refs = await seed(db, test_user, statements=("Первоначально я ИП",))
    for i in range(25):
        db.add(Message(chat_id=refs[0].chat_id, role="user", content=f"Уточнение {i}"))
    db.add(Message(chat_id=refs[0].chat_id, role="user", content="Позднее ИП закрыт"))
    await db.commit()
    context = await load_reference_user_context(db, user_id=test_user.id, reference=refs[0])
    assert context.startswith("Первоначально я ИП")
    assert context.endswith("Позднее ИП закрыт")
    assert "Учебный ответ" not in context
    assert await load_reference_user_context(db, user_id=999, reference=refs[0]) == ""


@pytest.mark.asyncio
async def test_source_text_cannot_prove_personal_status(db, test_user, monkeypatch):
    change, refs = await seed(db, test_user, statements=("Расскажите о правилах",))
    refs[0].source_text = "Я ИП"
    client, publisher = fake_client(monkeypatch, iter([("met", "Я ИП"), ("met", "Я ИП")]))
    assert await dispatcher.dispatch_law_change_notifications(db, check_personal_relevance=True) == 0
    assert await db.scalar(select(LawReferenceAssessment.error_code)) == "Evidence absent from user statements"
    publisher.assert_not_called()


@pytest.mark.asyncio
async def test_notification_metadata_persists_in_rest_after_read(db, test_user, monkeypatch, client):
    change, refs = await seed(db, test_user, statements=("Я ИП",))
    fake_client(monkeypatch, iter([("met", "Я ИП")]))
    assert await dispatcher.dispatch_law_change_notifications(db, check_personal_relevance=True) == 1
    response = await client.get("/notifications")
    assert response.status_code == 200
    note = response.json()[0]
    assert note["meta"]["law_change_id"] == change.id
    assert note["meta"]["chat_id"] == refs[0].chat_id
    assert note["meta"]["norms"][0]["article"] == "7"
    updated = await client.patch(f"/notifications/{note['id']}/read")
    assert updated.json()["meta"] == note["meta"]


@pytest.mark.asyncio
async def test_multiple_confirmed_chats_are_combined(db, test_user, monkeypatch):
    change, refs = await seed(db, test_user, statements=("Я ИП", "Я ИП"))
    client, publisher = fake_client(monkeypatch, iter([("met", "Я ИП"), ("met", "Я ИП")]))
    assert await dispatcher.dispatch_law_change_notifications(db, check_personal_relevance=True) == 1
    delivery = await db.scalar(select(LawChangeDelivery))
    assert delivery.payload_meta["reference_ids"] == [r.id for r in refs]
    assert delivery.payload_meta["related_chat_ids"] == sorted(r.chat_id for r in refs)
    assert set(await db.scalars(select(LawReferenceAssessment.notification_id))) == {delivery.notification_id}
    publisher.assert_called_once()


@pytest.mark.asyncio
async def test_inactive_user_is_not_checked_or_notified(db, test_user, monkeypatch):
    change, refs = await seed(db, test_user, statements=("Я ИП",))
    test_user.is_active = False
    await db.commit()
    mocked = AsyncMock()
    monkeypatch.setattr(dispatcher, "assess_law_reference_relevance", mocked)
    assert await dispatcher.dispatch_law_change_notifications(db, check_personal_relevance=True) == 0
    mocked.assert_not_called()
    assert list(await db.scalars(select(LawReferenceAssessment))) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("prior_status", [None, "irrelevant", "error"])
async def test_article_change_notice_needs_no_personal_analysis(db, test_user, monkeypatch, prior_status):
    change, refs = await seed(db, test_user, statements=("Я не ИП", "Вопрос о бизнесе сестры"))
    if prior_status:
        db.add(LawReferenceAssessment(change_id=change.id, reference_id=refs[0].id,
            status=prior_status, reason="Результат прежней проверки", conditions=[],
            model="fake", input_fingerprint="0" * 64, checked_at=datetime.now(timezone.utc)))
        await db.commit()
    calls = AsyncMock(side_effect=AssertionError("Article-change notices must not request GigaChat"))
    monkeypatch.setattr(dispatcher, "assess_law_reference_relevance", calls)
    monkeypatch.setattr(dispatcher, "assess_law_change_relevance", calls)
    monkeypatch.setattr(relevance, "get_gigachat_client", calls)
    publisher = Mock(side_effect=lambda *args, **kwargs: assert_committed(db))
    monkeypatch.setattr(dispatcher, "publish_notification", publisher)
    assert await dispatcher.dispatch_law_change_notifications(db) == 1
    note = await db.scalar(select(Notification))
    assert "Возможно, стоит пересмотреть прежний ответ" in note.message
    assert "Почему это касается вашей ситуации" not in note.message
    delivery = await db.scalar(select(LawChangeDelivery))
    assert delivery.payload_meta["notification_basis"] == "article_change"
    assert delivery.payload_meta["personal_relevance_checked"] is False
    assert delivery.payload_meta["reference_ids"] == [r.id for r in refs]
    assert delivery.payload_meta["related_chat_ids"] == sorted(r.chat_id for r in refs)
    assert len(delivery.payload_meta["norms"]) == 1
    saved = list(await db.scalars(select(LawReferenceAssessment)))
    assert len(saved) == (1 if prior_status else 0)
    if saved:
        assert saved[0].status == prior_status and saved[0].notification_id is None
    assert await dispatcher.dispatch_law_change_notifications(db) == 0
    publisher.assert_called_once()
    calls.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("article", "9"), ("part", "2"), ("document_key", "training:another-law")])
async def test_article_change_notice_requires_matching_norm(db, test_user, monkeypatch, field, value):
    change, refs = await seed(db, test_user, statements=("Учебный вопрос",))
    setattr(refs[0], field, value)
    await db.commit()
    publisher = Mock()
    monkeypatch.setattr(dispatcher, "publish_notification", publisher)
    assert await dispatcher.dispatch_law_change_notifications(db) == 0
    assert list(await db.scalars(select(Notification))) == []
    publisher.assert_not_called()


@pytest.mark.asyncio
async def test_article_notice_metadata_survives_rest_read(db, test_user, monkeypatch, client):
    change, refs = await seed(db, test_user, statements=("Вопрос о сроках",))
    publisher = Mock()
    monkeypatch.setattr(dispatcher, "publish_notification", publisher)
    assert await dispatcher.dispatch_law_change_notifications(db) == 1
    response = await client.get("/notifications")
    assert response.status_code == 200
    note = response.json()[0]
    assert note["meta"]["notification_basis"] == "article_change"
    assert note["meta"]["personal_relevance_checked"] is False
    assert note["meta"]["chat_id"] == refs[0].chat_id
    assert publisher.call_args.args[0]["meta"] == note["meta"]
    updated = await client.patch(f"/notifications/{note['id']}/read")
    assert updated.json()["meta"] == note["meta"]


@pytest.mark.asyncio
async def test_article_notice_commit_failure_never_publishes(db, test_user, monkeypatch):
    await seed(db, test_user, statements=("Вопрос о статье",))
    publisher = Mock()
    monkeypatch.setattr(dispatcher, "publish_notification", publisher)
    monkeypatch.setattr(db, "commit", AsyncMock(side_effect=RuntimeError("commit failed")))
    with pytest.raises(RuntimeError, match="commit failed"):
        await dispatcher.dispatch_law_change_notifications(db)
    publisher.assert_not_called()
    await db.rollback()
    assert list(await db.scalars(select(Notification))) == []


@pytest.mark.asyncio
async def test_auto_mapping_of_old_overview_is_not_lost_to_duplicates_or_age(db, test_user, monkeypatch):
    from app.services.law_change_parser import ParsedLawChange
    from app.services.law_change_monitor import persist_parsed_changes
    change, refs = await seed(db, test_user, statements=("Прежний вопрос",), scope=False)
    change.source_url = "https://www.consultant.ru/document/cons_doc_LAW_500/"
    change.created_at = datetime.now(timezone.utc) - timedelta(days=10)
    await db.commit()
    parsed = ParsedLawChange(title=change.change_title, change_date=change.change_date,
        description="Автоматически подтверждённая поправка", source_url=change.source_url,
        affected_norms=(NormIdentity("training:law", "7", "1"),),
        norm_evidence=({"method": "consultant_explicit_link", "target_label": "Часть 1 статьи 7"},))
    assert await persist_parsed_changes(db, [parsed]) == []
    assert change.diff["norm_mapping_pending"] is True
    publisher = Mock()
    monkeypatch.setattr(dispatcher, "publish_notification", publisher)
    assert await dispatcher.dispatch_law_change_notifications(db) == 1
    assert change.diff["norm_mapping_pending"] is False
    assert await persist_parsed_changes(db, [parsed]) == []
    assert change.diff["norm_mapping_pending"] is False
    assert await dispatcher.dispatch_law_change_notifications(db) == 0
    publisher.assert_called_once()


@pytest.mark.asyncio
async def test_document_change_notice_does_not_claim_article_changed(db, test_user, monkeypatch):
    change, refs = await seed(db, test_user, scope=False)
    await save_change_norms(db, change_id=change.id, norms=[NormIdentity("training:law")])
    monkeypatch.setattr(dispatcher, "publish_notification", Mock())
    assert await dispatcher.dispatch_law_change_notifications(db) == 1
    note = await db.scalar(select(Notification))
    assert "Изменение конкретной статьи пока не подтверждено" in note.message
    assert "Изменена норма" not in note.message
    assert await dispatcher.dispatch_law_change_notifications(db) == 0
