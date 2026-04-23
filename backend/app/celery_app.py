from celery import Celery
from celery.schedules import crontab
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.law_changes import LawDocument, LawChange
import httpx
import asyncio
from datetime import datetime, timedelta
import logging
from sqlalchemy import select

from app.models.notification import Notification
from app.models.user import User
from app.services.notification_bus import publish_notification

logger = logging.getLogger(__name__)

celery_app = Celery("legal_ai")
celery_app.conf.update(
    broker_url=settings.CELERY_BROKER_URL,
    result_backend=settings.CELERY_RESULT_BACKEND,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Europe/Moscow',
    enable_utc=True,
)

@celery_app.task(bind=True)
def monitor_law_changes(self):
    """Ежедневный мониторинг изменений законов"""
    async def check_gov_sources():
        async with AsyncSessionLocal() as db:
            # Парсинг pravo.gov.ru / consultant.ru API
            sources = [
                "https://pravo.gov.ru/proxy/ips/?search=ГК+РФ",  # Заглушка
                "https://api.you-right.ru/changes"  # Реальный API
            ]
            
            for source in sources:
                try:
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(source)
                        changes = resp.json().get('changes', [])
                        
                        for change in changes:
                            # Проверяем дубли
                            existing = await db.execute(
                                select(LawChange).where(
                                    LawChange.change_title == change['title']
                                )
                            )
                            if not existing.scalar():
                                new_change = LawChange(
                                    document_id=1,  # TODO: match document
                                    change_title=change['title'],
                                    change_date=datetime.fromisoformat(change['date']),
                                    description=change.get('description', ''),
                                    new_version=change.get('text', '')
                                )
                                db.add(new_change)
                        await db.commit()
                except Exception as e:
                    self.update_state(state='FAILURE', meta={'exc': str(e)})
    
    asyncio.run(check_gov_sources())
    send_notifications.delay()

@celery_app.task
def send_notifications():
    """Отправка уведомлений пользователям"""
    async def _send():
        async with AsyncSessionLocal() as db:
            # Берём изменения за последние 2 суток (на случай, если ежедневная задача была недоступна).
            since = datetime.utcnow() - timedelta(days=2)

            changes_result = await db.execute(
                select(LawChange)
                .where(LawChange.created_at >= since)
                .order_by(LawChange.created_at.asc())
            )
            changes = list(changes_result.scalars().all())
            if not changes:
                return

            users_result = await db.execute(select(User).where(User.is_active == True))  # noqa: E712
            users = list(users_result.scalars().all())
            if not users:
                return

            created_count = 0

            for change in changes:
                change_title = (change.change_title or "").strip() or "Изменение законодательства"
                # Детерминированный заголовок: позволяет легко не дублировать уведомления.
                title = f"LAW_CHANGE#{change.id}: {change_title}"

                date_str = None
                if change.change_date is not None:
                    try:
                        date_str = change.change_date.date().isoformat()
                    except Exception:
                        date_str = None

                description = (change.description or "").strip()
                if not description:
                    description = "Описание изменения не предоставлено источником."

                link = (change.source_url or "").strip()

                message_lines = [
                    f"📄 {change_title}",
                    f"📅 Дата: {date_str}" if date_str else None,
                    f"🔗 Источник: {link}" if link else None,
                    "",
                    "Что изменилось:",
                    description,
                ]
                message = "\n".join([line for line in message_lines if line is not None]).strip()

                for user in users:
                    # Идемпотентность: если такое уведомление уже есть — не создаём повторно.
                    exists_result = await db.execute(
                        select(Notification.id).where(
                            Notification.user_id == user.id,
                            Notification.notification_type == "law_change",
                            Notification.title == title,
                        )
                    )
                    if exists_result.scalar_one_or_none() is not None:
                        continue

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
                                "meta": {"law_change_id": change.id},
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

    asyncio.run(_send())

# Планировщик (каждый день в 9:00)
celery_app.conf.beat_schedule = {
    'monitor-laws-daily': {
        'task': 'app.celery_app.monitor_law_changes',
        'schedule': crontab(hour=9, minute=0),
    },
}
