from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api import auth
from app.schemas.auth import ResetPasswordRequest


@pytest.mark.asyncio
async def test_link_can_only_be_used_once(monkeypatch):
    redis = SimpleNamespace(getdel=AsyncMock(side_effect=['user@example.com', None]), aclose=AsyncMock())
    monkeypatch.setattr(auth.AsyncRedis, 'from_url', lambda *args, **kwargs: redis)
    account = SimpleNamespace(is_active=True)
    monkeypatch.setattr(auth.user, 'get_by_email', AsyncMock(return_value=account))
    update = AsyncMock()
    monkeypatch.setattr(auth.user, 'update_password', update)
    body = ResetPasswordRequest(token='test-token', new_password='NewPassword123')
    await auth.reset_password(body, db=None)
    with pytest.raises(HTTPException) as caught:
        await auth.reset_password(body, db=None)
    assert caught.value.status_code == 400
    update.assert_awaited_once()
    redis.getdel.assert_awaited_with('password_reset:test-token')


@pytest.mark.asyncio
async def test_inactive_account_cannot_reset(monkeypatch):
    redis = SimpleNamespace(getdel=AsyncMock(return_value='user@example.com'), aclose=AsyncMock())
    monkeypatch.setattr(auth.AsyncRedis, 'from_url', lambda *args, **kwargs: redis)
    monkeypatch.setattr(auth.user, 'get_by_email', AsyncMock(return_value=SimpleNamespace(is_active=False)))
    update = AsyncMock()
    monkeypatch.setattr(auth.user, 'update_password', update)
    with pytest.raises(HTTPException):
        await auth.reset_password(ResetPasswordRequest(token='test-token', new_password='NewPassword123'), db=None)
    update.assert_not_called()
