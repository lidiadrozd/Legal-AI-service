from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class CourtFiling(Base):
    __tablename__ = "court_filings"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    case_number: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    court_name: Mapped[str] = mapped_column(String(255), nullable=False)
    claim_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="submitted")
    tracking_number: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    documents: Mapped[list["CourtFilingDocument"]] = relationship(
        "CourtFilingDocument",
        back_populates="filing",
        cascade="all, delete-orphan",
    )


class CourtFilingDocument(Base):
    __tablename__ = "court_filing_documents"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    filing_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("court_filings.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    filing: Mapped["CourtFiling"] = relationship("CourtFiling", back_populates="documents")


__all__ = ["CourtFiling", "CourtFilingDocument"]
