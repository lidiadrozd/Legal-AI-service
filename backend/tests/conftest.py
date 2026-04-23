from collections.abc import AsyncGenerator
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.court_filings import router as court_filings_router
from app.api.deps import get_current_user
from app.api.documents import router as documents_router
from app.api.notifications import router as notifications_router
from app.db.base_class import Base
from app.db.session import get_db
from app.models.chat import ChatSession, Message
from app.models.court_filing import CourtFiling, CourtFilingDocument
from app.models.document import Document
from app.models.notification import Notification
from app.models.user import User


@pytest.fixture()
def test_user() -> User:
    user = User()
    user.id = 1
    user.email = "test@example.com"
    user.full_name = "Test User"
    user.hashed_password = "hashed"
    user.is_active = True
    user.is_superuser = False
    user.consent_given = True
    return user


@pytest_asyncio.fixture()
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[
                    User.__table__,
                    ChatSession.__table__,
                    Message.__table__,
                    CourtFiling.__table__,
                    CourtFilingDocument.__table__,
                    Notification.__table__,
                    Document.__table__,
                ],
            )
        )

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture()
async def client(db_session: AsyncSession, test_user: User):
    app = FastAPI(title="Test API")
    app.include_router(court_filings_router)
    app.include_router(notifications_router)
    app.include_router(documents_router)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    async def override_current_user() -> User:
        return test_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_current_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client
