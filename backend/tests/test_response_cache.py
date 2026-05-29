import pytest

from app.services.response_cache import build_cache_key, normalize_query


def test_normalize_query_collapses_whitespace_and_case():
    assert normalize_query("  Как   уволить  сотрудника? ") == "как уволить сотрудника?"


def test_build_cache_key_is_stable_for_same_input():
    first = build_cache_key(
        user_query="Как уволить сотрудника?",
        context={"rag": "контекст", "docs": []},
        chat_history="user: привет",
    )
    second = build_cache_key(
        user_query="  как   уволить сотрудника?",
        context={"rag": "контекст", "docs": []},
        chat_history="user: привет",
    )
    assert first == second


def test_build_cache_key_changes_with_history():
    base = build_cache_key(
        user_query="Как уволить сотрудника?",
        context=None,
        chat_history="user: первый вопрос",
    )
    changed = build_cache_key(
        user_query="Как уволить сотрудника?",
        context=None,
        chat_history="user: другой контекст",
    )
    assert base != changed


@pytest.mark.asyncio
async def test_response_cache_roundtrip(monkeypatch):
    from app.core.config import settings
    from app.services import response_cache as response_cache_module

    store: dict[str, str] = {}

    class FakeRedis:
        async def get(self, key: str):
            return store.get(key)

        async def set(self, key: str, value: str, ex: int | None = None):
            store[key] = value

    async def fake_get_client(self):
        return FakeRedis()

    monkeypatch.setattr(settings, "CHAT_RESPONSE_CACHE_ENABLED", True)
    monkeypatch.setattr(response_cache_module.ResponseCache, "_get_client", fake_get_client)

    cache = response_cache_module.ResponseCache()
    key = "legal_ai:chat_response:test"
    assert await cache.get(key) is None
    await cache.set(key, "cached answer")
    assert await cache.get(key) == "cached answer"
