from __future__ import annotations

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base_class import Base


class LlmUsageEvent(Base):
    __tablename__ = "llm_usage_events"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    chat_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("chat_sessions.id", ondelete="SET NULL"), index=True)
    message_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("messages.id", ondelete="SET NULL"), index=True)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    cached: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cogs_rub: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    usage_estimated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
