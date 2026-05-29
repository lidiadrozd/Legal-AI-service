from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.law_changes import LawChange
from app.models.notification import Notification
from app.models.user import User
from app.models.user_law_interest import UserLawInterest
from app.services.law_topic_service import build_change_search_text, change_matches_interest
from app.services.notification_bus import publish_notification

logger = logging.getLogger(__name__)


def _format_law_change_message(change: LawChange, topic_label: str) -> str:
    change_title = (change.change_title or "").strip() or "Изменение законодательства"
    date_str = None
    if change.change_date is not None:
        try:
            date_str = change.change_date.date().isoformat()
        except Exception:
            date_str = None
    description = (change.description or "").strip() or "Описание изменения не предоставлено источником."
    link = (change.source_url or "").strip()
    lines = [
        f"По теме «{topic_label}» обнаружено изменение законодательства.",
        f"📄 {change_title}",
        f"📅 Дата: {date_str}" if date_str else None,
        f"🔗 Источник: {link}" if link else None,
        "",
        "Что изменилось:",
        description,
    ]
    return "\n".join(line for line in lines if line is not None).strip()


async def dispatch_law_change_notifications(db: AsyncSession, *, lookback_days: int = 2) -> int:
    since = datetime.utcnow() - timedelta(days=lookback_days)
    changes_result = await db.execute(
        select(LawChange).where(LawChange.created_at >= since).order_by(LawChange.created_at.asc())
    )
    changes = list(changes_result.scalars().all())
    if not changes:
        return 0

    interests_result = await db.execute(select(UserLawInterest))
    interests = list(interests_result.scalars().all())
    if not interests:
        return 0

    users_result = await db.execute(select(User).where(User.is_active == True))  # noqa: E712
    active_users = {user.id: user for user in users_result.scalars().all()}
    created_count = 0

    for change in changes:
        category = None
        if isinstance(change.diff, dict):
            category = change.diff.get("category")
        change_text = build_change_search_text(
            title=change.change_title,
            description=change.description,
            category=category,
        )
        matched_users: dict[int, UserLawInterest] = {}
        for interest in interests:
            if not change_matches_interest(change_text, interest.keywords):
                continue
            if interest.user_id not in matched_users:
                matched_users[interest.user_id] = interest

        for user_id, interest in matched_users.items():
            user = active_users.get(user_id)
            if user is None:
                continue

            change_title = (change.change_title or "").strip() or "Изменение законодательства"
            title = f"LAW_CHANGE#{change.id}: {change_title}"
            exists_result = await db.execute(
                select(Notification.id).where(
                    Notification.user_id == user.id,
                    Notification.notification_type == "law_change",
                    Notification.title == title,
                )
            )
            if exists_result.scalar_one_or_none() is not None:
                continue

            message = _format_law_change_message(change, interest.topic_label)
            notification = Notification(
                user_id=user.id,
                title=title,
                message=message,
                notification_type="law_change",
                severity="medium",
                is_read=False,
            )
            db.add(notification)
            await db.flush()
            created_count += 1

            try:
                publish_notification(
                    {
                        "title": title,
                        "message": message,
                        "type": "law_change",
                        "severity": "medium",
                        "id": notification.id,
                        "meta": {
                            "law_change_id": change.id,
                            "chat_id": interest.chat_id,
                            "topic_key": interest.topic_key,
                            "topic_label": interest.topic_label,
                        },
                    },
                    user_id=user.id,
                )
            except Exception:
                logger.exception(
                    "Redis publish failed for law_change notification user_id=%s",
                    user.id,
                )

    if created_count > 0:
        await db.commit()
    return created_count
