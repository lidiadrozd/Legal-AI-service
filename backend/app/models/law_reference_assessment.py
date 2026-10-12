from datetime import datetime
from sqlalchemy import String, Text, JSON, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from app.db.base_class import Base


class LawReferenceAssessment(Base):
    __tablename__ = "law_reference_assessments"
    __table_args__ = (UniqueConstraint("change_id", "reference_id", name="uq_law_reference_assessment"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    change_id: Mapped[int] = mapped_column(ForeignKey("law_changes.id", ondelete="CASCADE"), index=True)
    reference_id: Mapped[int] = mapped_column(ForeignKey("chat_law_references.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str] = mapped_column(Text)
    conditions: Mapped[list] = mapped_column(JSON, default=list)
    law_analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    failure_stage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str] = mapped_column(String(100))
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    notification_id: Mapped[int | None] = mapped_column(ForeignKey("notifications.id", ondelete="SET NULL"), nullable=True)


class LawChangeDelivery(Base):
    __tablename__ = "law_change_deliveries"
    __table_args__ = (UniqueConstraint("user_id", "change_id", name="uq_law_change_delivery"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    change_id: Mapped[int] = mapped_column(ForeignKey("law_changes.id", ondelete="CASCADE"), index=True)
    notification_id: Mapped[int] = mapped_column(ForeignKey("notifications.id", ondelete="CASCADE"), unique=True)
    payload_meta: Mapped[dict] = mapped_column(JSON)
