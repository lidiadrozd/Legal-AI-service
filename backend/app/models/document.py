from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from app.db.base_class import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, index=True)  # uuid4 string
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title = Column(String(255), nullable=False)
    type = Column(String(50), nullable=False, default="upload")  # upload/generated/template
    status = Column(String(50), nullable=False, default="pending")  # pending/processing/ready/error

    file_path = Column(Text, nullable=True)  # absolute path
    file_size = Column(Integer, nullable=True)
    mime_type = Column(String(120), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


__all__ = ["Document"]

