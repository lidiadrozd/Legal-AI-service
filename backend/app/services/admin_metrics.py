from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import Date

from app.core.config import settings
from app.models.chat import ChatSession, Message
from app.models.llm_usage import LlmUsageEvent
from app.models.user import User
from app.schemas.admin import (
    AdminStatsResponse,
    AdminUserRow,
    CogsSummaryResponse,
    DailyStatPoint,
    DashboardStats,
    UserCogsRow,
)
from app.schemas.user import user_to_public


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def _avg_rating(db: AsyncSession) -> float:
    result = await db.execute(
        select(func.avg(case((Message.rating == "up", 1.0), else_=0.0))).where(Message.rating.is_not(None))
    )
    value = result.scalar_one_or_none()
    return float(value or 0.0)


async def _count_messages_today(db: AsyncSession) -> int:
    start = _utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(select(func.count(Message.id)).where(Message.created_at >= start))
    return int(result.scalar_one() or 0)


async def _count_active_users_today(db: AsyncSession) -> int:
    start = _utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.count(func.distinct(ChatSession.user_id))).where(ChatSession.updated_at >= start)
    )
    return int(result.scalar_one() or 0)


async def _usage_summary(db: AsyncSession) -> tuple[int, float, int, int]:
    result = await db.execute(
        select(
            func.coalesce(func.sum(LlmUsageEvent.total_tokens), 0),
            func.coalesce(func.sum(LlmUsageEvent.cogs_rub), 0.0),
            func.count(LlmUsageEvent.id),
            func.coalesce(func.sum(case((LlmUsageEvent.cached.is_(True), 1), else_=0)), 0),
        )
    )
    row = result.one()
    return int(row[0] or 0), float(row[1] or 0.0), int(row[2] or 0), int(row[3] or 0)


async def get_admin_stats(db: AsyncSession) -> AdminStatsResponse:
    total_users = int((await db.execute(select(func.count(User.id)))).scalar_one() or 0)
    total_chats = int((await db.execute(select(func.count(ChatSession.id)))).scalar_one() or 0)
    total_tokens, total_cogs_rub, _, cache_hits = await _usage_summary(db)

    summary = DashboardStats(
        total_users=total_users,
        total_chats=total_chats,
        messages_today=await _count_messages_today(db),
        avg_rating=await _avg_rating(db),
        active_users_today=await _count_active_users_today(db),
        total_tokens=total_tokens,
        total_cogs_rub=round(total_cogs_rub, 2),
        cache_hits=cache_hits,
    )

    start_day = (_utc_now() - timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)
    usage_day = cast(LlmUsageEvent.created_at, Date).label("day")
    usage_rows = (
        await db.execute(
            select(
                usage_day,
                func.coalesce(func.sum(LlmUsageEvent.total_tokens), 0),
                func.coalesce(func.sum(LlmUsageEvent.cogs_rub), 0.0),
            )
            .where(LlmUsageEvent.created_at >= start_day)
            .group_by(usage_day)
            .order_by(usage_day)
        )
    ).all()
    usage_by_day = {
        row[0].isoformat(): (int(row[1] or 0), float(row[2] or 0.0))
        for row in usage_rows
        if row[0] is not None
    }

    message_day = cast(Message.created_at, Date).label("day")
    message_rows = (
        await db.execute(
            select(message_day, func.count(Message.id))
            .where(Message.created_at >= start_day)
            .group_by(message_day)
            .order_by(message_day)
        )
    ).all()
    messages_by_day = {row[0].isoformat(): int(row[1] or 0) for row in message_rows if row[0] is not None}

    active_day = cast(ChatSession.updated_at, Date).label("day")
    active_rows = (
        await db.execute(
            select(active_day, func.count(func.distinct(ChatSession.user_id)))
            .where(ChatSession.updated_at >= start_day)
            .group_by(active_day)
            .order_by(active_day)
        )
    ).all()
    users_by_day = {row[0].isoformat(): int(row[1] or 0) for row in active_rows if row[0] is not None}

    daily: list[DailyStatPoint] = []
    for offset in range(30):
        day = (start_day + timedelta(days=offset)).date().isoformat()
        tokens_used, cogs_rub = usage_by_day.get(day, (0, 0.0))
        daily.append(
            DailyStatPoint(
                date=day,
                users=users_by_day.get(day, 0),
                messages=messages_by_day.get(day, 0),
                tokens_used=tokens_used,
                cogs_rub=round(cogs_rub, 2),
            )
        )

    return AdminStatsResponse(summary=summary, daily=daily)


async def get_admin_users(db: AsyncSession, *, search: str | None = None) -> list[AdminUserRow]:
    chat_count = func.count(func.distinct(ChatSession.id)).label("chat_count")
    tokens_used = func.coalesce(func.sum(LlmUsageEvent.total_tokens), 0).label("tokens_used")
    cogs_rub = func.coalesce(func.sum(LlmUsageEvent.cogs_rub), 0.0).label("cogs_rub")
    llm_requests = func.count(LlmUsageEvent.id).label("llm_requests")
    cache_hits = func.coalesce(func.sum(case((LlmUsageEvent.cached.is_(True), 1), else_=0)), 0).label("cache_hits")

    stmt = (
        select(User, chat_count, tokens_used, cogs_rub, llm_requests, cache_hits)
        .outerjoin(ChatSession, ChatSession.user_id == User.id)
        .outerjoin(LlmUsageEvent, LlmUsageEvent.user_id == User.id)
        .group_by(User.id)
        .order_by(User.id.asc())
    )
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where((User.email.ilike(pattern)) | (User.full_name.ilike(pattern)))

    rows = (await db.execute(stmt)).all()
    users: list[AdminUserRow] = []
    for user, chats, tokens, cogs, requests, hits in rows:
        public = user_to_public(user)
        users.append(
            AdminUserRow(
                id=public.id,
                email=public.email,
                full_name=public.full_name,
                role=public.role,
                is_active=public.is_active,
                is_consent_given=public.is_consent_given,
                created_at=public.created_at,
                chat_count=int(chats or 0),
                tokens_used=int(tokens or 0),
                cogs_rub=round(float(cogs or 0.0), 2),
                llm_requests=int(requests or 0),
                cache_hits=int(hits or 0),
            )
        )
    return users


async def get_cogs_summary(db: AsyncSession) -> CogsSummaryResponse:
    total_tokens, total_cogs_rub, llm_requests, cache_hits = await _usage_summary(db)
    users = await get_admin_users(db)
    user_rows = [
        UserCogsRow(
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            tokens_used=user.tokens_used,
            cogs_rub=user.cogs_rub,
            llm_requests=user.llm_requests,
            cache_hits=user.cache_hits,
        )
        for user in users
        if user.llm_requests > 0 or user.tokens_used > 0
    ]
    user_rows.sort(key=lambda item: item.cogs_rub, reverse=True)
    return CogsSummaryResponse(
        total_tokens=total_tokens,
        total_cogs_rub=round(total_cogs_rub, 2),
        llm_requests=llm_requests,
        cache_hits=cache_hits,
        price_per_1k_tokens=settings.GIGACHAT_PRICE_PER_1K_TOKENS,
        users=user_rows,
    )
