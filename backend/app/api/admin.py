from fastapi import APIRouter, Depends
from app.celery_app import monitor_law_changes

router = APIRouter(prefix="/admin", tags=["admin"])

@router.post("/monitor-laws")
async def trigger_law_monitoring():
    """Ручной запуск мониторинга"""
    task = monitor_law_changes.delay()
    return {"task_id": task.id, "status": "started"}
