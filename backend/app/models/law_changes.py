"""
Legal AI Service - Модели изменений законов
"""
from sqlalchemy import Integer, String, Text, DateTime, Boolean, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from typing import List, Optional

from app.db.base_class import Base

class LawDocument(Base):
    __tablename__ = "law_documents"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    number: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    full_text: Mapped[Optional[str]] = mapped_column(Text)
    source_url: Mapped[Optional[str]] = mapped_column(String(1000))
    published_at: Mapped[Optional[DateTime]] = mapped_column(DateTime(timezone=True))
    law_type: Mapped[Optional[str]] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="active")

    changes: Mapped[List["LawChange"]] = relationship("LawChange", back_populates="document")
    notifications: Mapped[List["LawNotification"]] = relationship("LawNotification", back_populates="document")

class LawChange(Base):
    __tablename__ = "law_changes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("law_documents.id"), index=True
    )
    change_title: Mapped[Optional[str]] = mapped_column(String(500))
    change_date: Mapped[Optional[DateTime]] = mapped_column(
        DateTime(timezone=True), index=True
    )
    old_version: Mapped[Optional[str]] = mapped_column(Text)
    new_version: Mapped[Optional[str]] = mapped_column(Text)
    diff: Mapped[Optional[dict]] = mapped_column(JSON)
    description: Mapped[Optional[str]] = mapped_column(Text)
    source_url: Mapped[Optional[str]] = mapped_column(String(1000))
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    document: Mapped["LawDocument"] = relationship("LawDocument", back_populates="changes")

class LawNotification(Base):
    __tablename__ = "law_notifications"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("law_documents.id"), index=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(500))
    message: Mapped[Optional[str]] = mapped_column(Text)
    sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    sent_at: Mapped[Optional[DateTime]] = mapped_column(DateTime(timezone=True))

    document: Mapped["LawDocument"] = relationship("LawDocument", back_populates="notifications")

__all__ = ["LawDocument", "LawChange", "LawNotification"]
