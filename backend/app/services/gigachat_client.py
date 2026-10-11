"""
GigaChat: Исправленный клиент с ручной сборкой заголовка Authorization.
"""
import time
import base64
import uuid
import httpx
import urllib3
from dataclasses import dataclass
from threading import Lock
from typing import Any

from app.core.config import settings
from app.services.llm_cost import TokenUsage, estimate_usage

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
_CHAT_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

@dataclass(frozen=True)
class ChatCompletionResult:
    content: str
    usage: TokenUsage

class GigaChatAutoToken:
    def __init__(self):
        self.access_token = None
        self.expires_at = 0
        self.lock = Lock()
        self.client_id = settings.GIGACHAT_CLIENT_ID
        self.client_secret = settings.GIGACHAT_CLIENT_SECRET

    def _build_auth_header(self) -> str:
        """Ручная сборка заголовка Basic Auth."""
        # Если секрет не указан, возможно пользователь вставил уже готовый Base64 в поле ID
        if not self.client_secret or len(self.client_id) > 50:
            auth_str = self.client_id
        else:
            # Классический способ: base64(ID:SECRET)
            raw_str = f"{self.client_id}:{self.client_secret}"
            auth_str = base64.b64encode(raw_str.encode("ascii")).decode("ascii")
        
        return f"Basic {auth_str}"

    async def _get_new_token(self) -> str:
        auth_header = self._build_auth_header()
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": str(uuid.uuid4()),
            "Authorization": auth_header
        }
        
        # Отладочный принт (поможет понять, что мы шлем)
        print(f"DEBUG: Sending Auth Header: {auth_header[:15]}...") 

        try:
            async with httpx.AsyncClient(verify=False, timeout=30.0) as http:
                response = await http.post(
                    _OAUTH_URL,
                    headers=headers,
                    data={"scope": settings.GIGACHAT_SCOPE},
                )
            
            if response.status_code != 200:
                print(f"❌ GigaChat OAuth Error {response.status_code}: {response.text}")
                response.raise_for_status()

            result = response.json()
            self.access_token = result['access_token']
            
            expires_in = result.get('expires_in', 1800)
            self.expires_at = time.time() + int(expires_in) - 60
            
            print(f"✅ GigaChat token updated. Valid until {time.ctime(self.expires_at)}")
            return self.access_token

        except Exception as e:
            print(f"🔥 Critical GigaChat OAuth error: {e}")
            raise

    async def chat_completion(self, messages, model, temperature=0.1) -> ChatCompletionResult:
        token = await self.get_valid_token()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        async with httpx.AsyncClient(verify=False, timeout=120.0) as http:
            r = await http.post(_CHAT_URL, headers=headers, json=payload)
        
        if r.status_code >= 400:
            raise RuntimeError(f"GigaChat Error {r.status_code}: {r.text}")
        
        data = r.json()
        content = data["choices"][0]["message"]["content"]
        usage_payload = data.get("usage", {})
        
        usage = TokenUsage(
            prompt_tokens=usage_payload.get("prompt_tokens", 0),
            completion_tokens=usage_payload.get("completion_tokens", 0),
            total_tokens=usage_payload.get("total_tokens", 0),
            usage_estimated=False
        )
        return ChatCompletionResult(content=content, usage=usage)

    async def get_valid_token(self) -> str:
        if time.time() >= self.expires_at - 60:
            await self._get_new_token()
        return self.access_token

_gigachat_client = None

async def get_gigachat_client() -> GigaChatAutoToken:
    global _gigachat_client
    if _gigachat_client is None:
        _gigachat_client = GigaChatAutoToken()
        await _gigachat_client._get_new_token()
    return _gigachat_client