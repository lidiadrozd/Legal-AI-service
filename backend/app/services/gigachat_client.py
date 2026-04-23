"""
GigaChat: OAuth и chat/completions через HTTP, как в официальных примерах Сбера
(auth=(CLIENT_ID, CLIENT_SECRET), scope в form-data, Bearer к чату).
"""
import time
from threading import Lock
import uuid
from typing import Any

import httpx
import urllib3

from app.core.config import settings

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
_CHAT_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"


class GigaChatAutoToken:
    def __init__(self):
        self.access_token = None
        self.expires_at = 0
        self.lock = Lock()
        self.client_id = settings.GIGACHAT_CLIENT_ID
        self.client_secret = settings.GIGACHAT_CLIENT_SECRET

    async def _get_new_token(self) -> str:
        """OAuth: Basic через auth=(client_id, client_secret), scope в теле."""
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": str(uuid.uuid4()),
        }
        try:
            async with httpx.AsyncClient(verify=False, timeout=30.0) as http:
                response = await http.post(
                    _OAUTH_URL,
                    headers=headers,
                    auth=(self.client_id, self.client_secret),
                    data={"scope": settings.GIGACHAT_SCOPE},
                )
            response.raise_for_status()
            result = response.json()
            
            self.access_token = result['access_token']
            # У разных контуров OAuth поля TTL могут отличаться.
            # Нормальный кейс: expires_in (секунды).
            # Fallback: expires_at (unix/ms) или безопасный TTL по умолчанию.
            expires_in = result.get('expires_in')
            if expires_in is not None:
                ttl_seconds = int(expires_in)
            else:
                expires_at_raw = result.get('expires_at')
                if expires_at_raw is not None:
                    expires_at_value = int(expires_at_raw)
                    # Если миллисекунды — конвертируем в секунды.
                    if expires_at_value > 10_000_000_000:
                        expires_at_value = expires_at_value // 1000
                    ttl_seconds = max(60, expires_at_value - int(time.time()))
                else:
                    # Консервативный fallback: 30 минут.
                    ttl_seconds = 1800

            self.expires_at = time.time() + ttl_seconds - 60  # Минус 1 минута
            print(f"OK GigaChat token until {time.ctime(self.expires_at)}")
            return self.access_token
        except httpx.HTTPStatusError as e:
            details = e.response.text if e.response is not None else "<no body>"
            print(f"GigaChat OAuth HTTP error: {e}; body={details}")
            raise RuntimeError(f"{e}; body={details}") from e
        except Exception as e:
            print(f"GigaChat OAuth error: {e}")
            raise

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        temperature: float = 0.1,
    ) -> str:
        """POST /v1/chat/completions с Bearer-токеном (как в curl/requests-примерах)."""
        token = await self.get_valid_token()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        }
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        async with httpx.AsyncClient(verify=False, timeout=120.0) as http:
            r = await http.post(_CHAT_URL, headers=headers, json=payload)
        if r.status_code >= 400:
            raise RuntimeError(f"GigaChat chat HTTP {r.status_code}: {r.text}")
        data = r.json()
        try:
            content = data["choices"][0]["message"]["content"]
            return content if isinstance(content, str) else str(content)
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"Unexpected GigaChat response: {data}") from e

    async def get_valid_token(self) -> str:
        """Возвращает валидный токен (обновляет при необходимости)"""
        with self.lock:
            # Проверяем: истек ли токен (с запасом 60 сек)
            if time.time() >= self.expires_at - 60:
                await self._get_new_token()
            return self.access_token

# Глобальный клиент (синглтон)
_gigachat_client = None

async def get_gigachat_client() -> GigaChatAutoToken:
    global _gigachat_client
    if _gigachat_client is None:
        _gigachat_client = GigaChatAutoToken()
        await _gigachat_client._get_new_token()  # Инициализация
    return _gigachat_client
