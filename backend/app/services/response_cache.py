from __future__ import annotations

import hashlib
import logging
import re

from redis.asyncio import Redis

from app.core.config import settings
from app.services.rag_context import serialize_chat_context

logger = logging.getLogger(__name__)

_CACHE_PREFIX = "legal_ai:chat_response:"
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_query(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", (text or "").strip().lower())


def build_cache_key(
    *,
    user_query: str,
    context: dict | str | None,
    chat_history: str,
    dialog_state: str = "",
) -> str:
    normalized_query = normalize_query(user_query)
    context_blob = serialize_chat_context(context)
    history_tail = (chat_history or "")[-settings.CHAT_RESPONSE_CACHE_HISTORY_CHARS :]
    payload = "\n".join(
        [
            settings.GIGACHAT_MODEL,
            normalized_query,
            context_blob,
            history_tail,
            dialog_state or "",
        ]
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{_CACHE_PREFIX}{digest}"


class ResponseCache:
    def __init__(self) -> None:
        self._client: Redis | None = None

    async def _get_client(self) -> Redis:
        if self._client is None:
            self._client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        return self._client

    async def get(self, key: str) -> str | None:
        if not settings.CHAT_RESPONSE_CACHE_ENABLED:
            return None
        try:
            client = await self._get_client()
            return await client.get(key)
        except Exception:
            logger.exception("Chat response cache read failed")
            return None

    async def set(self, key: str, value: str) -> None:
        if not settings.CHAT_RESPONSE_CACHE_ENABLED:
            return
        try:
            client = await self._get_client()
            await client.set(key, value, ex=settings.CHAT_RESPONSE_CACHE_TTL_SECONDS)
        except Exception:
            logger.exception("Chat response cache write failed")


response_cache = ResponseCache()
