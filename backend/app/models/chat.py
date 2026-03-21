"""
Legal AI Service - Chat модели БД
✅ SQLAlchemy 2.0 + Async совместимость + УНИКАЛЬНЫЕ ИМЕНА
"""
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from app.db.base_class import Base
from typing import List, Optional

class ChatSession(Base):
    """
    ✅ ChatSession вместо Chat (без конфликта с Pydantic ChatResponse)
    Таблица чатов пользователей
    """
    __tablename__ = "chat_sessions"  # ✅ Изменили название таблицы

    # ✅ SQLAlchemy 2.0 синтаксис
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[Optional[DateTime]] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(),
        onupdate=func.now()
    )

    # ✅ Связи (работают с async)
    messages: List["Message"] = relationship(
        "Message", 
        back_populates="chat_session",
        cascade="all, delete-orphan"
    )
    # owner = relationship("User", back_populates="chat_sessions")  # Временно

class Message(Base):
    """
    ✅ Сообщения чата (user/assistant)
    """
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)  # ✅ Text вместо String
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # "user", "assistant"
    chat_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        index=True
    )
    rating: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # "up", "down"
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # ✅ Связь с чатом
    chat_session: "ChatSession" = relationship(
        "ChatSession", 
        back_populates="messages"
    )

# ✅ Экспорт для использования
__all__ = ["ChatSession", "Message"]
