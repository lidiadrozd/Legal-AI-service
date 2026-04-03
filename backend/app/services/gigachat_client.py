"""
GigaChat Client с автоматическим обновлением токена
"""
import asyncio
import base64
import requests
import time
from typing import Optional
import urllib3
import uuid

from app.core.config import settings

# Для dev-среды: отключаем warning при verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class GigaChatAutoToken:
    def __init__(self):
        self.access_token: Optional[str] = None
        self.expires_at = 0.0
        # asyncio.Lock: не блокируем event loop при ожидании токена из другой корутины
        self._lock = asyncio.Lock()
        self.client_id = settings.GIGACHAT_CLIENT_ID
        self.client_secret = settings.GIGACHAT_CLIENT_SECRET
        self.auth_header = self._encode_auth()

    def _encode_auth(self) -> str:
        """Кодируем Client ID:Secret в Base64"""
        credentials = f"{self.client_id}:{self.client_secret}"
        return base64.b64encode(credentials.encode()).decode()

    async def _get_new_token(self) -> str:
        """Получаем новый токен (HTTP в thread pool, чтобы не блокировать event loop)."""
        url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": str(uuid.uuid4()),
            "Authorization": f"Basic {self.auth_header}",
        }
        data = f"scope={settings.GIGACHAT_SCOPE}"

        def _sync_fetch() -> dict:
            response = requests.post(
                url,
                headers=headers,
                data=data,
                timeout=15,
                verify=False,
            )
            response.raise_for_status()
            return response.json()

        try:
            result = await asyncio.to_thread(_sync_fetch)
            self.access_token = result["access_token"]
            expires_in = result.get("expires_in")
            if expires_in is not None:
                ttl_seconds = int(expires_in)
            else:
                expires_at_raw = result.get("expires_at")
                if expires_at_raw is not None:
                    expires_at_value = int(expires_at_raw)
                    if expires_at_value > 10_000_000_000:
                        expires_at_value = expires_at_value // 1000
                    ttl_seconds = max(60, expires_at_value - int(time.time()))
                else:
                    ttl_seconds = 1800

            self.expires_at = time.time() + ttl_seconds - 60
            print(f"✅ Новый GigaChat токен получен, истекает: {time.ctime(self.expires_at)}")
            return self.access_token
        except requests.HTTPError as e:
            details = ""
            try:
                details = e.response.text
            except Exception:
                details = "<no response body>"
            print(f"❌ Ошибка получения токена: {e}; body={details}")
            raise RuntimeError(f"{e}; body={details}") from e
        except Exception as e:
            print(f"❌ Ошибка получения токена: {e}")
            raise

    async def get_valid_token(self) -> str:
        """Возвращает валидный токен (обновляет при необходимости)."""
        async with self._lock:
            if time.time() >= self.expires_at - 60:
                await self._get_new_token()
            return self.access_token or ""


_gigachat_client: Optional[GigaChatAutoToken] = None


async def get_gigachat_client() -> GigaChatAutoToken:
    global _gigachat_client
    if _gigachat_client is None:
        _gigachat_client = GigaChatAutoToken()
        await _gigachat_client._get_new_token()
    return _gigachat_client
