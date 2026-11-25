
"""
GigaChat: получение OAuth-токена и выполнение chat/completions.
Использует асинхронные HTTP-запросы и проверку TLS-сертификатов.
"""

import asyncio
import base64
import binascii
import ipaddress
import json
import logging
import time
import uuid
import os
import socket
import ssl
from dataclasses import dataclass

import httpx
import certifi

from app.core.config import settings
from app.services.llm_cost import TokenUsage, estimate_usage


logger = logging.getLogger(__name__)

_OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
_CHAT_URL = "https://api.giga.chat/v1/chat/completions"
_CLOUDRU_HOST = "foundation-models.api.cloud.ru"
_CLOUDRU_CHAT_PATH = "/v1/chat/completions"
_FALLBACK_PROXY_CONNECT_ATTEMPTS = 4

# Запас времени перед истечением токена, чтобы не использовать
# токен на границе срока действия.
_TOKEN_REFRESH_MARGIN_SECONDS = 60


def build_gigachat_ssl_context() -> ssl.SSLContext:
    """Обычные доверенные CA плюс настроенный CA GigaChat; TLS всегда проверяется."""
    context = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE") or certifi.where())
    if settings.GIGACHAT_CA_BUNDLE_FILE:
        context.load_verify_locations(cafile=settings.GIGACHAT_CA_BUNDLE_FILE)
    return context


def _is_dns_resolution_error(exc: BaseException) -> bool:
    """Recognise Windows/Python DNS failures through the wrapped httpx chain."""
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, socket.gaierror):
            return True
        message = str(current).lower()
        if "getaddrinfo failed" in message or "name or service not known" in message:
            return True
        current = current.__cause__ or current.__context__
    return False


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
        self.chat_url = _CHAT_URL
        self.access_token: str | None = None
        self.expires_at: float = 0
        self.lock = asyncio.Lock()
        self._http_client: httpx.AsyncClient | None = None

        self.client_id = settings.GIGACHAT_CLIENT_ID
        self.client_secret = settings.GIGACHAT_CLIENT_SECRET

    def _get_http_client(self) -> httpx.AsyncClient:
        # Reuse established TLS connections across interview turns. Creating a
        # client per answer made every request depend on a new TLS handshake.
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(120.0, connect=15.0),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10, keepalive_expiry=120.0),
                proxy=getattr(settings, "GIGACHAT_PROXY_URL", "") or None,
                trust_env=False,
                verify=build_gigachat_ssl_context())
        return self._http_client

    async def aclose(self):
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def _connect_fallback_response(
        self,
        *,
        headers: dict[str, str],
        payload: dict,
        error: BaseException,
    ) -> httpx.Response | None:
        """Provider hook for a safe fallback after a connection failure."""
        return None

    async def _fallback_proxy_response(
        self,
        *,
        headers: dict[str, str],
        payload: dict,
        error: BaseException,
    ) -> httpx.Response | None:
        """Use the optional local proxy only after a direct connect failure."""
        if not isinstance(error, (httpx.ConnectError, httpx.ConnectTimeout)):
            return None
        proxy_url = settings.LLM_FALLBACK_PROXY_URL.strip()
        if not proxy_url:
            return None

        logger.warning("Прямой LLM-маршрут недоступен; используется fallback proxy")
        last_error: httpx.RequestError | None = None
        for attempt in range(_FALLBACK_PROXY_CONNECT_ATTEMPTS):
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(120.0, connect=15.0),
                    limits=httpx.Limits(
                        max_connections=10,
                        max_keepalive_connections=5,
                    ),
                    proxy=proxy_url,
                    trust_env=False,
                    verify=build_gigachat_ssl_context(),
                ) as http:
                    return await http.post(
                        self.chat_url,
                        headers=headers,
                        json=payload,
                    )
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                # Safe to retry: the connection was not established, hence the
                # POST was not sent.  Read/write timeouts are never retried.
                last_error = exc
                if attempt + 1 >= _FALLBACK_PROXY_CONNECT_ATTEMPTS:
                    raise
                # Happ/xray can drop its first CONNECT immediately after a
                # network/VPN route change.  Always recreate the client above
                # and give the local proxy a short moment before reconnecting.
                await asyncio.sleep(min(0.25 * (2 ** attempt), 1.0))
        if last_error is not None:
            raise last_error
        return None

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
            # OAuth must use the same explicitly configured CONNECT route as
            # chat/completions.  Otherwise a Docker Desktop installation can
            # reach the model endpoint through the local tunnel but fail
            # before that, while obtaining an access token.
            # Проверка TLS включена. Не отключайте её через verify=False.
            async with httpx.AsyncClient(
                timeout=30.0,
                proxy=getattr(settings, "GIGACHAT_PROXY_URL", "") or None,
                trust_env=False,
                verify=build_gigachat_ssl_context(),
            ) as http:
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
        max_tokens: int | None = None,
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
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        try:
            http = self._get_http_client()
            for attempt in range(2):
                try:
                    response = await http.post(self.chat_url, headers=headers, json=payload)
                    break
                except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                    # A failed connection has not sent a model request.  The
                    # local VPN/proxy can be switched while the process is
                    # running, leaving httpx's keep-alive pool unusable.  Do
                    # not retry through that same pool: close it and create a
                    # fresh client so the next attempt re-resolves the route.
                    # Never retry a read timeout or an ambiguous POST.
                    await self.aclose()
                    try:
                        fallback_response = await self._connect_fallback_response(
                            headers=headers,
                            payload=payload,
                            error=exc,
                        )
                    except (httpx.ConnectError, httpx.ConnectTimeout) as fallback_exc:
                        fallback_response = await self._fallback_proxy_response(
                            headers=headers,
                            payload=payload,
                            error=fallback_exc,
                        )
                    if fallback_response is not None:
                        response = fallback_response
                        break
                    fallback_response = await self._fallback_proxy_response(
                        headers=headers,
                        payload=payload,
                        error=exc,
                    )
                    if fallback_response is not None:
                        response = fallback_response
                        break
                    if attempt:
                        raise
                    http = self._get_http_client()

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


class CloudRuClient(GigaChatAutoToken):
    """Cloud.ru Foundation Models transport with the common completion interface."""

    def __init__(self):
        super().__init__()
        self.chat_url = f"https://{_CLOUDRU_HOST}{_CLOUDRU_CHAT_PATH}"

    async def get_valid_token(self) -> str:
        key = settings.CLOUDRU_API_KEY.strip()
        if not key:
            raise RuntimeError("Не задан CLOUDRU_API_KEY.")
        return key

    def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(120.0, connect=15.0),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
                # Cloud.ru is direct by default.  A workstation/VPN proxy is a
                # last-resort connect fallback, never a hard dependency.
                proxy=None,
                trust_env=False,
                # Cloud.ru is reached through the same Russian trust chain as
                # GigaChat on this workstation.  Reuse the project's CA
                # context instead of falling back to the host certifi bundle.
                verify=build_gigachat_ssl_context(),
            )
        return self._http_client

    async def _connect_fallback_response(
        self,
        *,
        headers: dict[str, str],
        payload: dict,
        error: BaseException,
    ) -> httpx.Response | None:
        # Do not bypass normal DNS or route other failures around it. This path
        # is solely for the reproducible Windows getaddrinfo failure.
        if not _is_dns_resolution_error(error):
            return None

        fallback_ip = settings.CLOUDRU_FALLBACK_IP.strip()
        if not fallback_ip:
            return None
        try:
            ipaddress.ip_address(fallback_ip)
        except ValueError:
            logger.error("Некорректный CLOUDRU_FALLBACK_IP; DNS fallback отключён")
            return None

        fallback_headers = dict(headers)
        fallback_headers["Host"] = _CLOUDRU_HOST
        fallback_url = f"https://{fallback_ip}{_CLOUDRU_CHAT_PATH}"
        logger.warning("Cloud.ru DNS недоступен; используется проверенный IP fallback")
        for attempt in range(2):
            http = self._get_http_client()
            request = http.build_request(
                "POST",
                fallback_url,
                headers=fallback_headers,
                json=payload,
            )
            # httpcore uses this hostname for both SNI and certificate validation,
            # so the fallback does not weaken TLS despite connecting to an IP.
            request.extensions["sni_hostname"] = _CLOUDRU_HOST
            try:
                return await http.send(request)
            except (httpx.ConnectError, httpx.ConnectTimeout):
                # These failures happen before the POST is sent. Recreate the
                # pool once; never repeat ambiguous read/write timeouts.
                await self.aclose()
                if attempt:
                    raise

        raise RuntimeError("Недостижимый код DNS fallback")

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float = 0.1,
        *,
        response_format: dict | None = None,
        structured_function: dict | None = None,
        max_tokens: int | None = None,
    ) -> ChatCompletionResult:
        if response_format is not None and structured_function is not None:
            raise ValueError("Choose one structured output mechanism")

        structured = response_format is not None or structured_function is not None
        if structured:
            schema = (
                structured_function.get("parameters", {})
                if structured_function
                else response_format
            )
            instruction = (
                "Верни только JSON-объект, без Markdown и пояснений. "
                "Соблюдай следующую спецификацию ответа: "
                + json.dumps(schema, ensure_ascii=False)
            )
            messages = [dict(message) for message in messages]
            if messages and messages[0].get("role") == "system":
                messages[0]["content"] += "\n" + instruction
            else:
                messages.insert(0, {"role": "system", "content": instruction})

        result = await super().chat_completion(
            messages,
            model=settings.CLOUDRU_MODEL,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if structured:
            try:
                parsed = json.loads(result.content)
            except (TypeError, ValueError):
                raise RuntimeError("Cloud.ru вернул некорректный JSON.") from None
            if not isinstance(parsed, dict):
                raise RuntimeError("Cloud.ru вернул JSON, не являющийся объектом.")
        return result


_gigachat_client: GigaChatAutoToken | None = None
_client_init_lock = asyncio.Lock()


async def close_gigachat_client():
    global _gigachat_client
    if _gigachat_client is not None:
        await _gigachat_client.aclose()
        _gigachat_client = None


async def get_gigachat_client() -> GigaChatAutoToken:
    """Возвращает общий экземпляр клиента GigaChat."""
    global _gigachat_client

    async with _client_init_lock:
        if _gigachat_client is None:
            _gigachat_client = (
                CloudRuClient()
                if settings.LLM_PROVIDER == "cloudru"
                else GigaChatAutoToken()
            )

        # Получаем токен до возврата клиента, чтобы ошибки подключения
        # обнаруживались при первом обращении.
        await _gigachat_client.get_valid_token()

        return _gigachat_client
