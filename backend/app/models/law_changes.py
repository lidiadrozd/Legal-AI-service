from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base_class import Base

class LawDocument(Base):
    __tablename__ = "law_documents"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)  # "ст. 421 ГК РФ"
    number = Column(String, unique=True)    # "421"
    full_text = Column(Text)
    source_url = Column(String)
    published_at = Column(DateTime(timezone=True))
    law_type = Column(String)  # "ГК РФ", "УК РФ", "ТК РФ"
    status = Column(String, default="active")  # active, archived
    
    changes = relationship("LawChange", back_populates="document")
    notifications = relationship("LawNotification", back_populates="document")

class LawChange(Base):
    __tablename__ = "law_changes"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("law_documents.id"))
    change_title = Column(String)  # "Изменения от 01.01.2026"
    change_date = Column(DateTime(timezone=True))
    old_version = Column(Text)
    new_version = Column(Text)
    diff = Column(JSON)  # {"added": [...], "removed": [...]}
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    document = relationship("LawDocument", back_populates="changes")

class LawNotification(Base):
    __tablename__ = "law_notifications"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("law_documents.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String)
    message = Column(Text)
    sent = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    sent_at = Column(DateTime(timezone=True), nullable=True)
    
    document = relationship("LawDocument")
    user = relationship("User")
