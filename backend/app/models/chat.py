"""
Legal AI Service - Chat модели БД
"""
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from typing import List, Optional

from app.db.base_class import Base

class ChatSession(Base):
    """
    ChatSession вместо Chat (без конфликта с Pydantic)
    Таблица чатов пользователей
    """
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[Optional[DateTime]] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    messages: Mapped[List["Message"]] = relationship(
        "Message",
        back_populates="chat_session",
        cascade="all, delete-orphan"
    )

class Message(Base):
    """
    Сообщения чата (user/assistant)
    """
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    chat_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        index=True
    )
    rating: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    chat_session: Mapped["ChatSession"] = relationship(
        "ChatSession",
        back_populates="messages"
    )

__all__ = ["ChatSession", "Message"]
