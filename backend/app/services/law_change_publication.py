from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.law_changes import LawChange

MAX_CHANGE_AGE_DAYS = 30
MIN_DESCRIPTION_LENGTH = 20


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def assess_law_change_publishability(
    change: LawChange,
    *,
    now: datetime | None = None,
) -> tuple[bool, str]:
    current = _as_utc(now or datetime.now(timezone.utc))
    title = (change.change_title or "").strip()
    if len(title) < 5:
        return False, "Отсутствует или слишком короткий заголовок изменения."

    if change.change_date is None:
        return False, "Не указана дата изменения."

    change_date = _as_utc(change.change_date)
    if change_date > current + timedelta(days=1):
        return False, "Дата изменения в будущем."

    if change_date < current - timedelta(days=MAX_CHANGE_AGE_DAYS):
        return False, "Изменение устарело для публикации пользователям."

    description = (change.description or "").strip()
    new_version = (change.new_version or "").strip()
    if len(description) < MIN_DESCRIPTION_LENGTH and len(new_version) < MIN_DESCRIPTION_LENGTH:
        return False, "Нет достаточного описания или текста изменения."

    source_url = (change.source_url or "").strip()
    if source_url and not source_url.startswith(("http://", "https://")):
        return False, "Некорректная ссылка на источник."

    return True, ""
