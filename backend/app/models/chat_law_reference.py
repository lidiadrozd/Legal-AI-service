"""Links to cited curated norms and explicit affected norms of a change."""
from datetime import datetime
from sqlalchemy import String, Text, ForeignKey, UniqueConstraint, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from app.db.base_class import Base


class ChatLawReference(Base):
    __tablename__ = "chat_law_references"
    __table_args__ = (UniqueConstraint("assistant_message_id", "document_key", "article", "part", "point",
                                      name="uq_chat_law_reference"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True)
    user_message_id: Mapped[int] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"))
    assistant_message_id: Mapped[int] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"))
    document_key: Mapped[str] = mapped_column(String(200), index=True)
    article: Mapped[str] = mapped_column(String(50), default="", server_default="")
    part: Mapped[str] = mapped_column(String(50), default="", server_default="")
    point: Mapped[str] = mapped_column(String(50), default="", server_default="")
    source_url: Mapped[str] = mapped_column(String(1000))
    source_revision: Mapped[str] = mapped_column(String(100))
    source_sha256: Mapped[str] = mapped_column(String(64))
    source_text: Mapped[str] = mapped_column(Text)
    situation_excerpt: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LawChangeNorm(Base):
    __tablename__ = "law_change_norms"
    __table_args__ = (UniqueConstraint("change_id", "document_key", "article", "part", "point",
                                      name="uq_law_change_norm"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    change_id: Mapped[int] = mapped_column(ForeignKey("law_changes.id", ondelete="CASCADE"), index=True)
    document_key: Mapped[str] = mapped_column(String(200), index=True)
    article: Mapped[str] = mapped_column(String(50), default="", server_default="")
    part: Mapped[str] = mapped_column(String(50), default="", server_default="")
    point: Mapped[str] = mapped_column(String(50), default="", server_default="")
