"""
GigaChat Client с автоматическим обновлением токена
"""
import asyncio
import base64
import requests
import time
from typing import Optional
from threading import Lock
from langchain_gigachat import GigaChat
from app.core.config import settings

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
            'RqUID': f"{int(time.time()*1000)}",  # Уникальный ID
            'Authorization': f'Basic {self.auth_header}'
        }
        data = 'scope=GIGACHAT_API_PERS'
        
        try:
            response = requests.post(url, headers=headers, data=data, timeout=10)
            response.raise_for_status()
            result = response.json()
            
            self.access_token = result['access_token']
            self.expires_at = time.time() + int(result['expires_in']) - 60  # Минус 1 минута
            print(f"✅ Новый GigaChat токен получен, истекает: {time.ctime(self.expires_at)}")
            return self.access_token
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
