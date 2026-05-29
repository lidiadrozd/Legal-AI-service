from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_superuser
from app.celery_app import monitor_law_changes
from app.db.session import get_db
from app.models.user import User
from app.schemas.admin import AdminStatsResponse, AdminUserRow, CogsSummaryResponse
from app.services.admin_metrics import get_admin_stats, get_admin_users, get_cogs_summary

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/monitor-laws")
async def trigger_law_monitoring(
    current_user: User = Depends(get_current_superuser),
):
    """Ручной запуск мониторинга"""
    task = monitor_law_changes.delay()
    return {"task_id": task.id, "status": "started", "started_by": current_user.email}


@router.get("/stats", response_model=AdminStatsResponse)
async def read_admin_stats(
    _: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    return await get_admin_stats(db)


@router.get("/users", response_model=list[AdminUserRow])
async def read_admin_users(
    search: str | None = None,
    _: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    return await get_admin_users(db, search=search)


@router.get("/cogs", response_model=CogsSummaryResponse)
async def read_cogs_summary(
    _: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    return await get_cogs_summary(db)
