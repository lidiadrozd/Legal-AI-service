
"""
GigaChat: получение OAuth-токена и выполнение chat/completions.
Использует асинхронные HTTP-запросы и проверку TLS-сертификатов.
"""

import asyncio
import base64
import binascii
import json
import logging
import time
import uuid
import os
import ssl
from dataclasses import dataclass

import httpx
import certifi

from app.core.config import settings
from app.services.llm_cost import TokenUsage, estimate_usage


logger = logging.getLogger(__name__)

_OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
_CHAT_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

# Запас времени перед истечением токена, чтобы не использовать
# токен на границе срока действия.
_TOKEN_REFRESH_MARGIN_SECONDS = 60


def build_gigachat_ssl_context() -> ssl.SSLContext:
    """Обычные доверенные CA плюс настроенный CA GigaChat; TLS всегда проверяется."""
    context = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE") or certifi.where())
    if settings.GIGACHAT_CA_BUNDLE_FILE:
        context.load_verify_locations(cafile=settings.GIGACHAT_CA_BUNDLE_FILE)
    return context


class GigaChatAPIError(RuntimeError):
    """Безопасный HTTP-статус без тела ответа и заголовков авторизации."""

    def __init__(self, status_code: int):
        self.status_code = status_code
        super().__init__(f"GigaChat HTTP {status_code}")


@dataclass(frozen=True)
class ChatCompletionResult:
    content: str
    usage: TokenUsage


class GigaChatAutoToken:
    """Клиент GigaChat с автоматическим обновлением OAuth-токена."""

    def __init__(self):
        self.access_token: str | None = None
        self.expires_at: float = 0
        self.lock = asyncio.Lock()

        self.client_id = settings.GIGACHAT_CLIENT_ID
        self.client_secret = settings.GIGACHAT_CLIENT_SECRET

    def _build_auth_header(self) -> str:
        """Accept an explicit ready-made key or a conventional ID/secret pair."""
        ready_key = getattr(settings, "GIGACHAT_AUTH_KEY", "").strip()
        if not ready_key and self.client_id and not self.client_secret:
            ready_key = self.client_id.strip()
        if ready_key:
            if ready_key.lower().startswith("basic "):
                ready_key = ready_key[6:].strip()
            try:
                decoded = base64.b64decode(ready_key, validate=True).decode("utf-8")
                client_id, separator, secret = decoded.partition(":")
                if not separator or not client_id or not secret:
                    raise ValueError("Invalid key")
            except (ValueError, UnicodeError, binascii.Error):
                raise RuntimeError("Некорректный формат ключа авторизации GigaChat.") from None
            return "Basic " + ready_key
        if not self.client_id or not self.client_secret:
            raise RuntimeError("Не заданы реквизиты авторизации GigaChat.")
        encoded = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode("utf-8")).decode("ascii")
        return "Basic " + encoded

    async def _get_new_token(self) -> str:
        """Получает новый OAuth-токен."""
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": str(uuid.uuid4()),
            "Authorization": self._build_auth_header(),
        }

        try:
            # Проверка TLS включена. Не отключайте её через verify=False.
            async with httpx.AsyncClient(timeout=30.0, verify=build_gigachat_ssl_context()) as http:
                response = await http.post(
                    _OAUTH_URL,
                    headers=headers,
                    data={"scope": settings.GIGACHAT_SCOPE},
                )

            response.raise_for_status()
            result = response.json()

            token = result.get("access_token")
            if not isinstance(token, str) or not token:
                raise RuntimeError(
                    "OAuth-сервис GigaChat не вернул access_token."
                )

            expires_in = result.get("expires_in")

            if expires_in is not None:
                ttl_seconds = int(expires_in)
            else:
                expires_at_raw = result.get("expires_at")

                if expires_at_raw is not None:
                    expires_at_value = int(expires_at_raw)

                    # Некоторые API возвращают время в миллисекундах.
                    if expires_at_value > 10_000_000_000:
                        expires_at_value //= 1000

                    ttl_seconds = max(
                        0,
                        expires_at_value - int(time.time()),
                    )
                else:
                    # Запасной вариант, если срок действия не указан.
                    ttl_seconds = 1800

            self.access_token = token
            self.expires_at = (
                time.time()
                + max(0, ttl_seconds - _TOKEN_REFRESH_MARGIN_SECONDS)
            )

            logger.info(
                "OAuth-токен GigaChat получен; срок действия около %s секунд",
                ttl_seconds,
            )

            return token

        except httpx.HTTPStatusError as exc:
            # Не записываем заголовки авторизации и секреты в журнал.
            logger.error(
                "Ошибка OAuth GigaChat: HTTP %s",
                exc.response.status_code,
            )
            raise RuntimeError(
                f"Ошибка получения OAuth-токена GigaChat: "
                f"HTTP {exc.response.status_code}"
            ) from exc

        except httpx.RequestError as exc:
            logger.error(
                "Ошибка сети при получении OAuth-токена GigaChat: %s",
                type(exc).__name__,
            )
            raise RuntimeError(
                "Не удалось подключиться к OAuth-сервису GigaChat."
            ) from exc

    async def get_valid_token(self) -> str:
        """Возвращает токен и при необходимости обновляет его."""
        async with self.lock:
            if (
                not self.access_token
                or time.time() >= self.expires_at
            ):
                await self._get_new_token()

            if not self.access_token:
                raise RuntimeError(
                    "Не удалось получить действующий токен GigaChat."
                )

            return self.access_token

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float = 0.1,
        *,
        response_format: dict | None = None,
        structured_function: dict | None = None,
    ) -> ChatCompletionResult:
        """Отправляет запрос модели и возвращает ответ с учётом токенов."""
        if response_format is not None and structured_function is not None:
            raise ValueError("Choose one structured output mechanism")
        token = await self.get_valid_token()

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        }

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if response_format is not None:
            payload["response_format"] = response_format
        if structured_function is not None:
            payload["functions"] = [structured_function]
            payload["function_call"] = {"name": structured_function["name"]}

        try:
            async with httpx.AsyncClient(timeout=120.0, verify=build_gigachat_ssl_context()) as http:
                response = await http.post(
                    _CHAT_URL,
                    headers=headers,
                    json=payload,
                )

            response.raise_for_status()
            data = response.json()

        except httpx.HTTPStatusError as exc:
            logger.error(
                "Ошибка chat/completions GigaChat: HTTP %s",
                exc.response.status_code,
            )
            raise GigaChatAPIError(exc.response.status_code) from exc

        except httpx.RequestError as exc:
            logger.error(
                "Ошибка сети при запросе к GigaChat: %s",
                type(exc).__name__,
            )
            raise RuntimeError(
                "Не удалось подключиться к API GigaChat."
            ) from exc

        try:
            message = data["choices"][0]["message"]
            if structured_function is not None:
                function_call = message.get("function_call")
                if (not isinstance(function_call, dict)
                        or function_call.get("name") != structured_function["name"]):
                    raise RuntimeError("GigaChat did not return the requested structured function")
                arguments = function_call.get("arguments")
                if isinstance(arguments, dict):
                    content = json.dumps(arguments, ensure_ascii=False)
                elif isinstance(arguments, str):
                    content = arguments
                else:
                    raise RuntimeError("GigaChat returned invalid structured arguments")
            else:
                content = message["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                "GigaChat вернул ответ в неожиданном формате."
            ) from exc

        if not isinstance(content, str):
            content = str(content)

        usage_payload = (
            data.get("usage")
            if isinstance(data.get("usage"), dict)
            else {}
        )

        prompt_tokens = int(usage_payload.get("prompt_tokens") or 0)
        completion_tokens = int(
            usage_payload.get("completion_tokens") or 0
        )
        total_tokens = int(usage_payload.get("total_tokens") or 0)

        if (
            prompt_tokens == 0
            and completion_tokens == 0
            and total_tokens == 0
        ):
            prompt_text = "\n".join(
                str(message.get("content", ""))
                for message in messages
            )
            usage = estimate_usage(
                prompt_text=prompt_text,
                completion_text=content,
            )
        else:
            if total_tokens <= 0:
                total_tokens = prompt_tokens + completion_tokens

            usage = TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                usage_estimated=False,
            )

        return ChatCompletionResult(
            content=content,
            usage=usage,
        )


_gigachat_client: GigaChatAutoToken | None = None
_client_init_lock = asyncio.Lock()


async def get_gigachat_client() -> GigaChatAutoToken:
    """Возвращает общий экземпляр клиента GigaChat."""
    global _gigachat_client

    async with _client_init_lock:
        if _gigachat_client is None:
            _gigachat_client = GigaChatAutoToken()

        # Получаем токен до возврата клиента, чтобы ошибки подключения
        # обнаруживались при первом обращении.
        await _gigachat_client.get_valid_token()

        return _gigachat_client
