from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base_class import Base
from app.models.chat import ChatSession, Message
from app.services.law_user_context import load_law_user_context, MAX_CONTEXT_CHARS


@pytest_asyncio.fixture
async def context_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(lambda conn: Base.metadata.create_all(
            conn, tables=[ChatSession.__table__, Message.__table__]))
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            db.add_all([ChatSession(id=10, user_id=1), ChatSession(id=20, user_id=2)])
            await db.commit()
            yield db
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_only_own_statements_in_chronological_order(context_db):
    now = datetime.utcnow()
    context_db.add_all([
        Message(chat_id=10, role="user", content="Я работал как ИП.", created_at=now),
        Message(chat_id=10, role="assistant", content="Вы действующий ИП.", created_at=now),
        Message(chat_id=10, role="user", content="Уточнение: ИП закрыт.", created_at=now + timedelta(seconds=1)),
        Message(chat_id=20, role="user", content="Чужая ситуация", created_at=now),
    ])
    await context_db.commit()
    assert await load_law_user_context(context_db, user_id=1, chat_id=10) == (
        "Я работал как ИП.\n\nУточнение: ИП закрыт.")
    assert await load_law_user_context(context_db, user_id=1, chat_id=20) == ""
    assert await load_law_user_context(context_db, user_id=1, chat_id=None) == ""
    assert await load_law_user_context(context_db, user_id=1, chat_id=999) == ""


@pytest.mark.asyncio
async def test_message_limit_keeps_latest_twenty(context_db):
    now = datetime.utcnow()
    for index in range(25):
        context_db.add(Message(chat_id=10, role="user", content=f"Факт {index}",
                               created_at=now + timedelta(seconds=index)))
    await context_db.commit()
    text = await load_law_user_context(context_db, user_id=1, chat_id=10)
    assert text.split("\n\n") == [f"Факт {index}" for index in range(5, 25)]


@pytest.mark.asyncio
async def test_character_budget_preserves_latest_correction(context_db):
    now = datetime.utcnow()
    context_db.add_all([
        Message(chat_id=10, role="user", content="x" * 10000, created_at=now),
        Message(chat_id=10, role="user", content="ИП закрыт.", created_at=now + timedelta(seconds=1)),
    ])
    await context_db.commit()
    text = await load_law_user_context(context_db, user_id=1, chat_id=10)
    assert len(text) == MAX_CONTEXT_CHARS
    assert text.endswith("\n\nИП закрыт.")
