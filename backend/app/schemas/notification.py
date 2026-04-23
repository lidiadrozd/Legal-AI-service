from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class NotificationSeverity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class NotificationCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=255, examples=["Изменение статуса подачи в суд"])
    message: str = Field(..., min_length=3, examples=["Ваше заявление принято канцелярией суда"])
    notification_type: str | None = Field(default="system", max_length=50)
    severity: NotificationSeverity = NotificationSeverity.medium


class NotificationOut(BaseModel):
    id: int
    title: str
    message: str
    notification_type: str | None = None
    severity: str | None = None
    is_read: bool
    read_at: datetime | None = None
    created_at: datetime

    class Config:
        from_attributes = True
