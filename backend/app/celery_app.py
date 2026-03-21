from celery import Celery
from celery.schedules import crontab
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.law_changes import LawDocument, LawChange
import httpx
import asyncio
from datetime import datetime, timedelta

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
    # TODO: Email/SMS через SMTP/Telegram Bot
    print("🔔 Отправка уведомлений о изменениях законов")

# Планировщик (каждый день в 9:00)
celery_app.conf.beat_schedule = {
    'monitor-laws-daily': {
        'task': 'app.celery_app.monitor_law_changes',
        'schedule': crontab(hour=9, minute=0),
    },
}
