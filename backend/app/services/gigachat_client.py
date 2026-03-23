"""
GigaChat Client с автоматическим обновлением токена
"""
import asyncio
import base64
import requests
import time
from typing import Optional
from threading import Lock
import urllib3
import uuid

from app.core.config import settings

# Для dev-среды: отключаем warning при verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class GigaChatAutoToken:
    def __init__(self):
        self.access_token = None
        self.expires_at = 0
        self.lock = Lock()
        self.client_id = settings.GIGACHAT_CLIENT_ID
        self.client_secret = settings.GIGACHAT_CLIENT_SECRET
        self.auth_header = self._encode_auth()
        
    def _encode_auth(self) -> str:
        """Кодируем Client ID:Secret в Base64"""
        credentials = f"{self.client_id}:{self.client_secret}"
        return base64.b64encode(credentials.encode()).decode()
    
    async def _get_new_token(self) -> str:
        """Получаем новый токен"""
        url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json',
            'RqUID': str(uuid.uuid4()),  # Уникальный UUID запроса
            'Authorization': f'Basic {self.auth_header}'
        }
        data = f"scope={settings.GIGACHAT_SCOPE}"
        
        try:
            response = requests.post(
                url,
                headers=headers,
                data=data,
                timeout=10,
                verify=False,  # Для dev-среды (SSL цепочка может быть недоступна локально)
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
