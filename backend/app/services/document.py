from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: int
    title: str
    type: str
    status: str
    file_path: str | None = None
    file_size: int | None = None
    mime_type: str | None = None
    generation_meta: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime | None = None


class UploadDocumentResponse(BaseModel):
    document_id: str
    filename: str
    status: str


class GenerateDocumentRequest(BaseModel):
    template_key: str = Field(..., min_length=2, max_length=100)
    filename: str = Field(..., min_length=3, max_length=255)
    fields: dict[str, Any] = Field(default_factory=dict)
    output_format: str = Field(default="docx", pattern="^(docx|txt|pdf)$")
    template_version: int | None = Field(default=None, ge=1)
    chat_id: int | None = Field(default=None, ge=1)
    court_filing_id: int | None = Field(default=None, ge=1)


class SuggestDocumentFieldsRequest(BaseModel):
    template_key: str = Field(..., min_length=2, max_length=100)
    chat_id: int | None = Field(default=None, ge=1)
    court_filing_id: int | None = Field(default=None, ge=1)


class SuggestDocumentFieldsResponse(BaseModel):
    suggested: dict[str, str]
    sources: dict[str, str]
    template_version: int


class DocumentTemplateFieldOut(BaseModel):
    key: str
    label: str
    multiline: bool = False
    pattern: str | None = None


class DocumentTemplateOut(BaseModel):
    key: str
    version: int
    title: str
    description: str
    fields: list[DocumentTemplateFieldOut]
