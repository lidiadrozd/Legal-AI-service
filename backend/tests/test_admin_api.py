import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.admin import router as admin_router
from app.api.deps import get_current_user
from app.models.user import User


class _FakeTaskResult:
    id = "task-123"


class _FakeTask:
    @staticmethod
    def delay():
        return _FakeTaskResult()


@pytest_asyncio.fixture()
async def admin_client(monkeypatch):
    app = FastAPI(title="Admin Test API")
    app.include_router(admin_router)

    monkeypatch.setattr("app.api.admin.monitor_law_changes", _FakeTask())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield app, client


@pytest.mark.asyncio
async def test_admin_route_rejects_regular_user(admin_client):
    app, client = admin_client

    async def override_regular_user() -> User:
        user = User()
        user.email = "user@example.com"
        user.is_superuser = False
        return user

    app.dependency_overrides[get_current_user] = override_regular_user
    response = await client.post("/admin/monitor-laws")
    assert response.status_code == 403
    assert response.json()["detail"] == "Superadmin privileges required"


@pytest.mark.asyncio
async def test_admin_route_allows_superadmin(admin_client):
    app, client = admin_client

    async def override_superuser() -> User:
        user = User()
        user.email = "root@example.com"
        user.is_superuser = True
        return user

    app.dependency_overrides[get_current_user] = override_superuser
    response = await client.post("/admin/monitor-laws")
    assert response.status_code == 200
    body = response.json()
    assert body["task_id"] == "task-123"
    assert body["status"] == "started"
    assert body["started_by"] == "root@example.com"
