from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.text import capitalize_filename, capitalize_first_letter


DocumentType = Literal["upload", "generated", "template"]
DocumentStatus = Literal["pending", "processing", "ready", "error"]


class DocumentOut(BaseModel):
    id: str
    user_id: str
    title: str
    type: DocumentType
    status: DocumentStatus
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("user_id", mode="before")
    @classmethod
    def _user_id_to_str(cls, v: object) -> str:
        if v is None:
            return ""
        return str(v)

    @field_validator("title", mode="before")
    @classmethod
    def _normalize_title(cls, v: object) -> str:
        s = "" if v is None else str(v).strip()
        if not s:
            return "Документ"
        return capitalize_filename(s)


class UploadDocumentResponse(BaseModel):
    document_id: str
    filename: str
    status: DocumentStatus

    @field_validator("filename", mode="before")
    @classmethod
    def _normalize_filename(cls, v: object) -> str:
        s = "" if v is None else str(v).strip()
        if not s:
            return "Документ"
        return capitalize_filename(s)


class DocumentGenerateRequest(BaseModel):
    document_type: str = Field(..., min_length=2, max_length=120)  # "исковое заявление", "договор"...
    user_query: str = Field(..., min_length=2, max_length=2000)
    output_format: Literal["docx", "pdf"] = "docx"
    template_id: Optional[str] = None
    client_data: dict = Field(default_factory=dict)
    title: Optional[str] = None

    @field_validator("document_type", mode="before")
    @classmethod
    def _cap_document_type(cls, v: object) -> str:
        s = str(v).strip() if v is not None else ""
        return capitalize_first_letter(s) if s else s

    @field_validator("title", mode="before")
    @classmethod
    def _cap_optional_title(cls, v: object) -> Optional[str]:
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        return capitalize_filename(s)

