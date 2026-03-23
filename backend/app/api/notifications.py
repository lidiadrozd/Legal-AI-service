import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import NotificationCreate, NotificationOut

router = APIRouter(prefix="/notifications", tags=["Notifications"])
logger = logging.getLogger(__name__)


@router.get(
    "",
    response_model=list[NotificationOut],
    summary="Список уведомлений текущего пользователя",
    responses={401: {"description": "Требуется авторизация"}},
)
async def list_notifications(
    is_read: bool | None = Query(default=None, description="Фильтрация по признаку прочитано/непрочитано"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Notification).where(Notification.user_id == current_user.id)
    if is_read is not None:
        stmt = stmt.where(Notification.is_read == is_read)
    stmt = stmt.order_by(Notification.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post(
    "",
    response_model=NotificationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать уведомление для текущего пользователя",
    responses={
        201: {"description": "Уведомление создано"},
        422: {"description": "Ошибка валидации запроса"},
    },
)
async def create_notification(
    payload: NotificationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    notification = Notification(
        user_id=current_user.id,
        title=payload.title,
        message=payload.message,
        notification_type=payload.notification_type,
        severity=payload.severity.value,
        is_read=False,
    )
    db.add(notification)
    await db.commit()
    await db.refresh(notification)
    logger.info("Notification created: notification_id=%s user_id=%s", notification.id, current_user.id)
    return notification


@router.patch(
    "/{notification_id}/read",
    response_model=NotificationOut,
    summary="Отметить уведомление как прочитанное",
    responses={
        404: {"description": "Уведомление не найдено"},
    },
)
async def mark_notification_as_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    notification = result.scalar_one_or_none()
    if not notification:
        logger.warning(
            "Notification not found: notification_id=%s user_id=%s",
            notification_id,
            current_user.id,
        )
        raise HTTPException(status_code=404, detail="Notification not found")

    if not notification.is_read:
        from datetime import datetime, timezone

        notification.is_read = True
        notification.read_at = datetime.now(timezone.utc)
        db.add(notification)
        await db.commit()
        await db.refresh(notification)

    logger.info("Notification marked read: notification_id=%s user_id=%s", notification_id, current_user.id)
    return notification
