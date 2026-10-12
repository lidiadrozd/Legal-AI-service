from celery import Celery
from celery.schedules import crontab
import asyncio
import logging

from sqlalchemy import select
from app.models.law_monitor_state import LawMonitorState

from app.core.config import settings
from app.db.session import AsyncSessionLocal, engine
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


def run_async_task(operation):
    async def run():
        try:
            return await operation
        finally:
            # Each asyncio.run owns a fresh event loop. Do not carry asyncpg
            # connections from a closed loop into the next task in this worker.
            await engine.dispose()
    return asyncio.run(run())


@celery_app.task(bind=True)
def monitor_law_changes(self):
    """Ежедневный мониторинг изменений законов."""
    try:
        created = run_async_task(monitor_sources())
        logger.info("Law monitoring completed, new changes: %s", len(created))
    except Exception as exc:
        logger.exception("Law monitoring failed")
        self.update_state(state="FAILURE", meta={"exc": str(exc)})
        raise
    send_notifications.delay()


async def retry_failed_sources():
    """Read persistent failures so retries also survive worker restarts."""
    configured = settings.law_change_source_list()
    if not configured:
        return None
    async with AsyncSessionLocal() as db:
        failed = list(await db.scalars(select(LawMonitorState.source_url).where(
            LawMonitorState.source_url.in_(configured),
            LawMonitorState.last_error.is_not(None),
        )))
    if not failed:
        return None
    return await monitor_sources(source_urls=failed)


@celery_app.task
def retry_law_monitoring():
    """Retry failed sources; leave successfully checked sources alone."""
    created = run_async_task(retry_failed_sources())
    if created is None:
        logger.info("Law monitoring retry skipped: no failed sources")
        return
    logger.info("Law monitoring retry completed, new changes: %s", len(created))
    # Existing changes may have acquired a precise norm even with no new rows.
    send_notifications.delay()


@celery_app.task
def send_notifications():
    """Уведомления об изменении норм, использованных в прежних ответах."""

    async def _send() -> int:
        async with AsyncSessionLocal() as db:
            return await dispatch_law_change_notifications(db)

    created_count = run_async_task(_send())
    logger.info("Law change notifications created: %s", created_count)


celery_app.conf.beat_schedule = {
    "retry-failed-law-sources": {
        "task": "app.celery_app.retry_law_monitoring",
        "schedule": crontab(hour="10,12,15", minute=0),
    },
    "monitor-laws-daily": {
        "task": "app.celery_app.monitor_law_changes",
        "schedule": crontab(hour=9, minute=0),
    },
}
