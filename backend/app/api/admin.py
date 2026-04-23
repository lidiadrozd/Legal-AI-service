from fastapi import APIRouter, Depends
from app.celery_app import monitor_law_changes
from app.api.deps import get_current_superuser
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["admin"])

@router.post("/monitor-laws")
async def trigger_law_monitoring(
    current_user: User = Depends(get_current_superuser),
):
    """Ручной запуск мониторинга"""
    task = monitor_law_changes.delay()
    return {"task_id": task.id, "status": "started", "started_by": current_user.email}
