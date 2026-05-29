"""
SaluteSpeech: OAuth и синхронное распознавание (REST speech:recognize).
Документация: https://developers.sber.ru/docs/ru/salutespeech/rest/sync-general
"""

from __future__ import annotations

import logging
import time
import uuid
from threading import Lock
from typing import Any

import httpx
import urllib3

from app.core.config import settings

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

_OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
_RECOGNIZE_URL = "https://smartspeech.sber.ru/rest/v1/speech:recognize"


def _client_id() -> str:
    return (settings.SALUTE_SPEECH_CLIENT_ID or settings.GIGACHAT_CLIENT_ID or "").strip()


def _client_secret() -> str:
    return (settings.SALUTE_SPEECH_CLIENT_SECRET or settings.GIGACHAT_CLIENT_SECRET or "").strip()


def is_salute_speech_configured() -> bool:
    return bool(_client_id() and _client_secret())


class SaluteSpeechTokenClient:
    def __init__(self) -> None:
        self.access_token: str | None = None
        self.expires_at = 0.0
        self._lock = Lock()

    async def _fetch_token(self) -> str:
        client_id = _client_id()
        client_secret = _client_secret()
        if not client_id or not client_secret:
            raise RuntimeError(
                "SaluteSpeech не настроен: укажите SALUTE_SPEECH_CLIENT_ID и SALUTE_SPEECH_CLIENT_SECRET "
                "(или те же GIGACHAT_CLIENT_ID / GIGACHAT_CLIENT_SECRET со scope SaluteSpeech)"
            )

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": str(uuid.uuid4()),
        }
        async with httpx.AsyncClient(verify=False, timeout=30.0) as http:
            response = await http.post(
                _OAUTH_URL,
                headers=headers,
                auth=(client_id, client_secret),
                data={"scope": settings.SALUTE_SPEECH_SCOPE},
            )
        response.raise_for_status()
        result = response.json()

        self.access_token = result["access_token"]
        expires_in = result.get("expires_in")
        if expires_in is not None:
            ttl = int(expires_in)
        else:
            ttl = 1800
        self.expires_at = time.time() + ttl - 60
        return self.access_token

    async def get_valid_token(self) -> str:
        with self._lock:
            if not self.access_token or time.time() >= self.expires_at - 60:
                await self._fetch_token()
            assert self.access_token
            return self.access_token


_token_client: SaluteSpeechTokenClient | None = None


async def get_salute_speech_token_client() -> SaluteSpeechTokenClient:
    global _token_client
    if _token_client is None:
        _token_client = SaluteSpeechTokenClient()
    return _token_client


def _extract_text_from_response(data: Any) -> str:
    if data is None:
        return ""
    if isinstance(data, str):
        return data.strip()
    if isinstance(data, list):
        parts = [_extract_text_from_response(item) for item in data]
        return " ".join(p for p in parts if p).strip()
    if isinstance(data, dict):
        for key in ("text", "normalized_text", "raw_text"):
            if key in data and data[key]:
                return str(data[key]).strip()
        if "result" in data:
            return _extract_text_from_response(data["result"])
        if "results" in data:
            return _extract_text_from_response(data["results"])
        if "hypotheses" in data:
            return _extract_text_from_response(data["hypotheses"])
    return ""


async def recognize_pcm(
    pcm: bytes,
    *,
    sample_rate: int | None = None,
    language: str = "ru-RU",
) -> str:
    if not pcm:
        raise ValueError("Пустой аудиопоток")

    rate = sample_rate or settings.SALUTE_SPEECH_SAMPLE_RATE
    token_client = await get_salute_speech_token_client()
    token = await token_client.get_valid_token()

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": f"audio/x-pcm;bit=16;rate={rate}",
        "Accept": "application/json",
    }
    params = {"language": language}

    async with httpx.AsyncClient(verify=False, timeout=120.0) as http:
        response = await http.post(
            _RECOGNIZE_URL,
            headers=headers,
            params=params,
            content=pcm,
        )

    if response.status_code >= 400:
        logger.error("SaluteSpeech recognize HTTP %s: %s", response.status_code, response.text)
        raise RuntimeError(f"SaluteSpeech: ошибка {response.status_code}")

    try:
        body = response.json()
    except Exception:
        text = response.text.strip()
        if text:
            return text
        raise RuntimeError("SaluteSpeech: не удалось разобрать ответ") from None

    text = _extract_text_from_response(body)
    if not text:
        raise RuntimeError("SaluteSpeech: пустой результат распознавания")
    return text
