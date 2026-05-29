from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.llm_usage import LlmUsageEvent


@dataclass(frozen=True)
class TokenUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    usage_estimated: bool


def estimate_tokens(text: str) -> int:
    normalized = (text or "").strip()
    if not normalized:
        return 0
    return max(1, int(len(normalized) / 3.5))


def estimate_usage(*, prompt_text: str, completion_text: str) -> TokenUsage:
    prompt_tokens = estimate_tokens(prompt_text)
    completion_tokens = estimate_tokens(completion_text)
    return TokenUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        usage_estimated=True,
    )


def calculate_cogs_rub(total_tokens: int, *, cached: bool = False) -> float:
    if cached or total_tokens <= 0:
        return 0.0
    return round((total_tokens / 1000.0) * settings.GIGACHAT_PRICE_PER_1K_TOKENS, 4)


async def record_llm_usage(
    db: AsyncSession,
    *,
    user_id: int,
    chat_id: int | None,
    message_id: int | None,
    model: str,
    cached: bool,
    usage: TokenUsage,
) -> LlmUsageEvent:
    event = LlmUsageEvent(
        user_id=user_id,
        chat_id=chat_id,
        message_id=message_id,
        model=model,
        cached=cached,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        total_tokens=usage.total_tokens,
        cogs_rub=calculate_cogs_rub(usage.total_tokens, cached=cached),
        usage_estimated=usage.usage_estimated,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event
