
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base_class import Base
from app.models.chat import ChatSession, Message
from app.models.chat_law_reference import ChatLawReference, LawChangeNorm
from app.models.law_reference_assessment import LawReferenceAssessment, LawChangeDelivery
from app.models.law_changes import LawChange, LawDocument
from app.models.notification import Notification
from app.models.user import User
from app.models.user_law_interest import UserLawInterest
from app.services.law_relevance_service import LawRelevanceResult
from app.services.law_notification_service import dispatch_law_change_notifications


@pytest.mark.asyncio
async def test_relevant_change_creates_notification_once():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    tables = [
        User.__table__,
        ChatSession.__table__,
        Message.__table__,
        LawDocument.__table__,
        LawChange.__table__,
        UserLawInterest.__table__,
        Notification.__table__,
        ChatLawReference.__table__, LawChangeNorm.__table__,
        LawReferenceAssessment.__table__, LawChangeDelivery.__table__,
    ]

    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda conn: Base.metadata.create_all(conn, tables=tables)
            )

        async with session_factory() as db:
            user = User(
                id=501,
                email="law-test@example.com",
                full_name="Test User",
                hashed_password="not-a-real-password",
                is_active=True,
                is_superuser=False,
                consent_given=True,
            )
            db.add(user)

            chat = ChatSession(id=601, user_id=user.id)
            db.add(chat)

            document = LawDocument(
                id=701,
                title="Тестовый нормативный документ",
                number="TEST-LAW-701",
                status="active",
            )
            db.add(document)
            await db.flush()

            change = LawChange(
                id=801,
                document_id=document.id,
                change_title="Изменение страховых взносов для ИП",
                change_date=datetime.utcnow(),
                description="Изменены сроки уплаты страховых взносов индивидуальными предпринимателями.",
                source_url="https://example.com/test-law",
                diff={"category": "налоги и взносы"},
                created_at=datetime.utcnow(),
            )
            db.add(change)

            interest = UserLawInterest(
                id=901,
                user_id=user.id,
                chat_id=chat.id,
                topic_key="individual_entrepreneur",
                topic_label="Индивидуальный предприниматель",
                keywords=["ИП", "страховые взносы", "налоги"],
                source_excerpt="Я ИП и слежу за налогами и взносами.",
            )
            db.add(interest)
            db.add(Message(chat_id=chat.id, role="user", content="Я ИП в Свердловской области."))
            await db.commit()

            with (
                patch(
                    "app.services.law_notification_service.assess_law_change_relevance",
                    new=AsyncMock(
                        return_value=LawRelevanceResult(
                            relevant=True,
                            reason="Изменение касается страховых взносов ИП.",
                        )
                    ),
                ) as relevance_mock,
                patch(
                    "app.services.law_notification_service.publish_notification"
                ) as publish_mock,
            ):
                first_count = await dispatch_law_change_notifications(
                    db, lookback_days=2, legacy_keyword_fallback=True
                )
                second_count = await dispatch_law_change_notifications(
                    db, lookback_days=2, legacy_keyword_fallback=True
                )

            result = await db.execute(
                select(Notification).where(
                    Notification.user_id == user.id,
                    Notification.notification_type == "law_change",
                )
            )
            notifications = list(result.scalars().all())

            assert first_count == 1
            assert second_count == 0
            assert len(notifications) == 1
            assert notifications[0].is_read is False
            publish_mock.assert_called_once()
            assert relevance_mock.call_args.kwargs["user_context"] == "Я ИП в Свердловской области."

    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("result_status", ["irrelevant", "insufficient_data", "error"])
async def test_irrelevant_change_does_not_create_notification(result_status):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    tables = [
        User.__table__,
        ChatSession.__table__,
        Message.__table__,
        LawDocument.__table__,
        LawChange.__table__,
        UserLawInterest.__table__,
        Notification.__table__,
        ChatLawReference.__table__, LawChangeNorm.__table__,
        LawReferenceAssessment.__table__, LawChangeDelivery.__table__,
    ]

    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda conn: Base.metadata.create_all(conn, tables=tables)
            )

        async with session_factory() as db:
            user = User(
                id=1501,
                email="irrelevant-test@example.com",
                full_name="Test User",
                hashed_password="not-a-real-password",
                is_active=True,
                is_superuser=False,
                consent_given=True,
            )
            chat = ChatSession(id=1601)
            document = LawDocument(
                id=1701,
                title="Тестовый документ",
                number="TEST-LAW-1701",
                status="active",
            )
            db.add_all([user, chat, document])
            await db.flush()

            change = LawChange(
                id=1801,
                document_id=document.id,
                change_title="Изменение страховых взносов для ИП",
                description="Изменены сроки уплаты страховых взносов.",
                diff={"category": "налоги и взносы"},
                created_at=datetime.utcnow(),
            )
            interest = UserLawInterest(
                id=1901,
                user_id=user.id,
                chat_id=chat.id,
                topic_key="individual_entrepreneur",
                topic_label="Индивидуальный предприниматель",
                keywords=["ИП", "страховые взносы", "налоги"],
                source_excerpt="Я ИП и слежу за налогами.",
            )
            db.add_all([change, interest])
            await db.commit()

            with (
                patch(
                    "app.services.law_notification_service.assess_law_change_relevance",
                    new=AsyncMock(
                        return_value=LawRelevanceResult(
                            relevant=False,
                            reason="Изменение не влияет на интересы пользователя.",
                            status=result_status,
                        )
                    ),
                ),
                patch(
                    "app.services.law_notification_service.publish_notification"
                ) as publish_mock,
            ):
                created_count = await dispatch_law_change_notifications(
                    db, lookback_days=2, legacy_keyword_fallback=True
                )

            result = await db.execute(
                select(Notification).where(
                    Notification.user_id == user.id,
                    Notification.notification_type == "law_change",
                )
            )

            assert created_count == 0
            assert result.scalars().all() == []
            publish_mock.assert_not_called()

    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_gigachat_error_does_not_create_notification():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    tables = [
        User.__table__,
        ChatSession.__table__,
        Message.__table__,
        LawDocument.__table__,
        LawChange.__table__,
        UserLawInterest.__table__,
        Notification.__table__,
        ChatLawReference.__table__, LawChangeNorm.__table__,
        LawReferenceAssessment.__table__, LawChangeDelivery.__table__,
    ]

    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda conn: Base.metadata.create_all(conn, tables=tables)
            )

        async with session_factory() as db:
            user = User(
                id=2501,
                email="gigachat-error-test@example.com",
                full_name="Test User",
                hashed_password="not-a-real-password",
                is_active=True,
                is_superuser=False,
                consent_given=True,
            )
            chat = ChatSession(id=2601)
            document = LawDocument(
                id=2701,
                title="Тестовый документ",
                number="TEST-LAW-2701",
                status="active",
            )
            db.add_all([user, chat, document])
            await db.flush()

            change = LawChange(
                id=2801,
                document_id=document.id,
                change_title="Изменение страховых взносов для ИП",
                description="Изменены сроки уплаты страховых взносов.",
                diff={"category": "налоги и взносы"},
                created_at=datetime.utcnow(),
            )
            interest = UserLawInterest(
                id=2901,
                user_id=user.id,
                chat_id=chat.id,
                topic_key="individual_entrepreneur",
                topic_label="Индивидуальный предприниматель",
                keywords=["ИП", "страховые взносы", "налоги"],
                source_excerpt="Я ИП и слежу за налогами.",
            )
            db.add_all([change, interest])
            await db.commit()

            with (
                patch(
                    "app.services.law_notification_service.assess_law_change_relevance",
                    new=AsyncMock(
                        side_effect=Exception("GigaChat недоступен")
                    ),
                ),
                patch(
                    "app.services.law_notification_service.publish_notification"
                ) as publish_mock,
            ):
                with pytest.raises(Exception, match="GigaChat недоступен"):
                    await dispatch_law_change_notifications(
                        db, lookback_days=2, legacy_keyword_fallback=True
                    )

            result = await db.execute(
                select(Notification).where(
                    Notification.user_id == user.id,
                    Notification.notification_type == "law_change",
                )
            )

            assert result.scalars().all() == []
            publish_mock.assert_not_called()

    finally:
        await engine.dispose()
