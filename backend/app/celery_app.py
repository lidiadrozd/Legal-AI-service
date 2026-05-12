Фfrom celery import Celery
from celery.schedules import crontab
import asyncio
import logging

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.services.law_change_monitor import monitor_sources
from app.services.law_notification_service import dispatch_law_change_notifications

logger = logging.getLogger(__name__)

celery_app = Celery("legal_ai")
celery_app.conf.update(
    broker_url=settings.CELERY_BROKER_URL,
    result_backend=settings.CELERY_RESULT_BACKEND,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Moscow",
    enable_utc=True,
)


@celery_app.task(bind=True)
def monitor_law_changes(self):
    """Ежедневный мониторинг изменений законов."""
    try:
        created = asyncio.run(monitor_sources())
        logger.info("Law monitoring completed, new changes: %s", len(created))
    except Exception as exc:
        logger.exception("Law monitoring failed")
        self.update_state(state="FAILURE", meta={"exc": str(exc)})
        raise
    send_notifications.delay()


@celery_app.task
def send_notifications():
    """Отправка уведомлений пользователям по темам из чатов."""

    async def _send() -> int:
        async with AsyncSessionLocal() as db:
            return await dispatch_law_change_notifications(db)

    created_count = asyncio.run(_send())
    logger.info("Law change notifications created: %s", created_count)


celery_app.conf.beat_schedule = {
    "monitor-laws-daily": {
        "task": "app.celery_app.monitor_law_changes",
        "schedule": crontab(hour=9, minute=0),
    },
}
