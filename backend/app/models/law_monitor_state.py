"""Operational checkpoints for source recovery, not a catalog of legal norms."""
from datetime import datetime
from sqlalchemy import String, DateTime, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base_class import Base


class LawMonitorState(Base):
    __tablename__ = "law_monitor_states"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_url: Mapped[str] = mapped_column(String(1000), unique=True, nullable=False)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(100))
    coverage_gap: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    progress: Mapped[dict] = mapped_column(JSON, default=dict)
