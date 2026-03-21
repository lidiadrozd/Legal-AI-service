"""
Legal AI Service - Модели изменений законов (Задача 241949)
✅ Совместимо с Async SQLAlchemy 2.0 + исправленные импорты
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base  # ✅ Совместимость
from app.db.base_class import Base  # ✅ Импорт исправленного Base
from typing import List, Optional

class LawDocument(Base):
    __tablename__ = "law_documents"
    
    # ✅ SQLAlchemy 2.0 стиль (опционально)
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)      # "ст. 421 ГК РФ"
    number: Mapped[str] = mapped_column(String(50), unique=True, index=True)  # "421"
    full_text: Mapped[Optional[Text]] = mapped_column(Text)
    source_url: Mapped[Optional[str]] = mapped_column(String(1000))
    published_at: Mapped[Optional[DateTime]] = mapped_column(DateTime(timezone=True))
    law_type: Mapped[Optional[str]] = mapped_column(String(100))         # "ГК РФ", "УК РФ"
    status: Mapped[str] = mapped_column(String(20), default="active")    # active/archived
    
    # ✅ Связи (работают с async)
    changes: List["LawChange"] = relationship("LawChange", back_populates="document")
    notifications: List["LawNotification"] = relationship("LawNotification", back_populates="document")

class LawChange(Base):
    __tablename__ = "law_changes"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("law_documents.id"), index=True
    )
    change_title: Mapped[Optional[str]] = mapped_column(String(500))      # "Изменения от 01.01.2026"
    change_date: Mapped[Optional[DateTime]] = mapped_column(
        DateTime(timezone=True), index=True
    )
    old_version: Mapped[Optional[Text]] = mapped_column(Text)
    new_version: Mapped[Optional[Text]] = mapped_column(Text)
    diff: Mapped[Optional[dict]] = mapped_column(JSON)                    # {"added": [...], "removed": [...]}
    description: Mapped[Optional[Text]] = mapped_column(Text)
    source_url: Mapped[Optional[str]] = mapped_column(String(1000))
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    
    # ✅ Связь (работает с async)
    document: "LawDocument" = relationship("LawDocument", back_populates="changes")

class LawNotification(Base):
    __tablename__ = "law_notifications"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("law_documents.id"), index=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), index=True
    )
    title: Mapped[Optional[str]] = mapped_column(String(500))
    message: Mapped[Optional[Text]] = mapped_column(Text)
    sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    sent_at: Mapped[Optional[DateTime]] = mapped_column(DateTime(timezone=True))
    
    # ✅ Связи (безопасные для async)
    document: "LawDocument" = relationship("LawDocument", back_populates="notifications")
    # user: "User" = relationship("User")  # ✅ Временно отключено (если нет models/user.py)

# ✅ Экспорт для __init__.py
__all__ = ["LawDocument", "LawChange", "LawNotification"]
