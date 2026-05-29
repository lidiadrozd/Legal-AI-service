import pytest

from app.services.llm_cost import TokenUsage, calculate_cogs_rub, estimate_tokens, estimate_usage


def test_estimate_tokens_from_text_length():
    assert estimate_tokens("1234567890") >= 2


def test_calculate_cogs_rub_uses_configured_price(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "GIGACHAT_PRICE_PER_1K_TOKENS", 0.065)
    assert calculate_cogs_rub(1000) == 0.065
    assert calculate_cogs_rub(0) == 0.0
    assert calculate_cogs_rub(1000, cached=True) == 0.0


def test_estimate_usage_marks_payload_as_estimated():
    usage = estimate_usage(prompt_text="system prompt", completion_text="answer")
    assert usage.total_tokens == usage.prompt_tokens + usage.completion_tokens
    assert usage.usage_estimated is True


@pytest.mark.asyncio
async def test_record_llm_usage_persists_event(db_session):
    from app.models.llm_usage import LlmUsageEvent
    from app.models.user import User
    from app.services.llm_cost import record_llm_usage

    user = User(
        email="usage@example.com",
        full_name="Usage User",
        hashed_password="hashed",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    event = await record_llm_usage(
        db_session,
        user_id=user.id,
        chat_id=None,
        message_id=None,
        model="GigaChat",
        cached=False,
        usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150, usage_estimated=False),
    )

    assert event.id is not None
    assert event.cogs_rub > 0

    stored = await db_session.get(LlmUsageEvent, event.id)
    assert stored is not None
    assert stored.total_tokens == 150
