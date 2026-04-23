from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class FilingStatus(str, Enum):
    submitted = "submitted"
    received = "received"
    in_review = "in_review"
    accepted = "accepted"
    rejected = "rejected"


class CourtDocumentIn(BaseModel):
    filename: str = Field(..., examples=["iskovoe-zayavlenie.pdf"])
    mime_type: str = Field(..., examples=["application/pdf"])
    size_bytes: int = Field(..., ge=1, le=25 * 1024 * 1024, examples=[102400])

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        allowed_ext = (".pdf", ".doc", ".docx", ".rtf")
        if not value.lower().endswith(allowed_ext):
            raise ValueError("Unsupported document format. Allowed: .pdf, .doc, .docx, .rtf")
        return value

    @field_validator("mime_type")
    @classmethod
    def validate_mime_type(cls, value: str) -> str:
        allowed = {
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/rtf",
            "text/rtf",
        }
        if value not in allowed:
            raise ValueError("Unsupported MIME type for court filing document")
        return value


class CourtFilingCreate(BaseModel):
    case_number: str = Field(..., min_length=3, max_length=128, examples=["А40-12345/2026"])
    court_name: str = Field(..., min_length=3, max_length=255, examples=["Арбитражный суд г. Москвы"])
    claim_type: str = Field(..., min_length=2, max_length=100, examples=["Исковое заявление"])
    documents: list[CourtDocumentIn] = Field(..., min_length=1, max_length=20)


class CourtDocumentOut(BaseModel):
    id: int
    filename: str
    mime_type: str
    size_bytes: int

    class Config:
        from_attributes = True


class CourtFilingOut(BaseModel):
    id: int
    case_number: str
    court_name: str
    claim_type: str
    status: FilingStatus
    tracking_number: str
    comment: str | None = None
    created_at: datetime
    documents: list[CourtDocumentOut]

    class Config:
        from_attributes = True


class CourtFilingStatusUpdate(BaseModel):
    status: FilingStatus
    comment: str | None = Field(default=None, max_length=1000)
