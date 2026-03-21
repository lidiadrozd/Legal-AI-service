from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base_class import Base
from sqlalchemy.dialects.postgresql import UUID

class LawDocument(Base):
    __tablename__ = "law_documents"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)           # "ст. 421 ГК РФ"
    number = Column(String(50), unique=True, index=True)  # "421"
    full_text = Column(Text)
    source_url = Column(String(1000))
    published_at = Column(DateTime(timezone=True))
    law_type = Column(String(100))                        # "ГК РФ", "УК РФ"
    status = Column(String(20), default="active")         # active/archived
    
    # Связи
    changes = relationship("LawChange", back_populates="document")
    notifications = relationship("LawNotification", back_populates="document")

class LawChange(Base):
    __tablename__ = "law_changes"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("law_documents.id"), index=True)
    change_title = Column(String(500))                    # "Изменения от 01.01.2026"
    change_date = Column(DateTime(timezone=True), index=True)
    old_version = Column(Text)
    new_version = Column(Text)
    diff = Column(JSON)                                   # {"added": [...], "removed": [...]}
    description = Column(Text)
    source_url = Column(String(1000))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Связь
    document = relationship("LawDocument", back_populates="changes")

class LawNotification(Base):
    __tablename__ = "law_notifications"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("law_documents.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    title = Column(String(500))
    message = Column(Text)
    sent = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    sent_at = Column(DateTime(timezone=True), nullable=True)
    
    # Связи
    document = relationship("LawDocument", back_populates="notifications")
    user = relationship("User")
