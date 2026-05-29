import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.admin import router as admin_router
from app.api.deps import get_current_superuser
from app.db.base_class import Base
from app.db.session import get_db
from app.models.chat import ChatSession, Message
from app.models.llm_usage import LlmUsageEvent
from app.models.user import User
from app.services.llm_cost import TokenUsage, record_llm_usage


@pytest_asyncio.fixture()
async def admin_db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[User.__table__, ChatSession.__table__, Message.__table__, LlmUsageEvent.__table__],
            )
        )

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture()
async def admin_client(admin_db_session: AsyncSession):
    app = FastAPI(title="Admin COGS Test API")
    app.include_router(admin_router)

    async def override_get_db():
        yield admin_db_session

    async def override_superuser() -> User:
        user = User()
        user.id = 1
        user.email = "root@example.com"
        user.full_name = "Root"
        user.is_superuser = True
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_superuser] = override_superuser

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client, admin_db_session


@pytest.mark.asyncio
async def test_admin_cogs_returns_user_breakdown(admin_client):
    client, db = admin_client

    user = User(
        email="client@example.com",
        full_name="Client",
        hashed_password="hashed",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    await record_llm_usage(
        db,
        user_id=user.id,
        chat_id=None,
        message_id=None,
        model="GigaChat",
        cached=False,
        usage=TokenUsage(100, 50, 150, False),
    )
    await record_llm_usage(
        db,
        user_id=user.id,
        chat_id=None,
        message_id=None,
        model="GigaChat",
        cached=True,
        usage=TokenUsage(0, 0, 0, False),
    )

    response = await client.get("/admin/cogs")
    assert response.status_code == 200
    body = response.json()
    assert body["total_tokens"] == 150
    assert body["llm_requests"] == 2
    assert body["cache_hits"] == 1
    assert len(body["users"]) == 1
    assert body["users"][0]["email"] == "client@example.com"
