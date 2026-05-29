from __future__ import annotations

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base_class import Base


class UserLawInterest(Base):
    __tablename__ = "user_law_interests"
    __table_args__ = (
        UniqueConstraint("user_id", "chat_id", "topic_key", name="uq_user_law_interests_user_chat_topic"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    chat_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=True, index=True
    )
    topic_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    topic_label: Mapped[str] = mapped_column(String(200), nullable=False)
    keywords: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    source_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


__all__ = ["UserLawInterest"]
