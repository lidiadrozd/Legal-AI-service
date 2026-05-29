import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user
from app.api.speech import router as speech_router
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
async def speech_client(test_user: User):
    app = FastAPI()
    app.include_router(speech_router)

    async def override_current_user() -> User:
        return test_user

    app.dependency_overrides[get_current_user] = override_current_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_transcribe_success(speech_client, monkeypatch):
    def _fake_pcm(*_args, **_kwargs):
        return b"\x00\x00" * 100

    async def _fake_recognize(*_args, **_kwargs):
        return "Привет, это тест распознавания"

    monkeypatch.setattr("app.api.speech.is_salute_speech_configured", lambda: True)
    monkeypatch.setattr("app.api.speech.transcode_to_pcm16", _fake_pcm)
    monkeypatch.setattr("app.api.speech.recognize_pcm", _fake_recognize)

    response = await speech_client.post(
        "/speech/transcribe",
        files={"audio": ("test.webm", b"fake-audio", "audio/webm")},
    )
    assert response.status_code == 200
    assert response.json()["text"] == "Привет, это тест распознавания"


@pytest.mark.asyncio
async def test_transcribe_not_configured(speech_client, monkeypatch):
    monkeypatch.setattr("app.api.speech.is_salute_speech_configured", lambda: False)

    response = await speech_client.post(
        "/speech/transcribe",
        files={"audio": ("test.webm", b"fake", "audio/webm")},
    )
    assert response.status_code == 503
