from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class StartDocumentInterview(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    prompt: str = Field(min_length=3, max_length=20000)
    chat_id: int | None = Field(default=None, ge=1)
    start_request_id: UUID | None = None
    new_case: bool = False
    title: str = Field(default="", max_length=200)
    document_type: str = Field(default="", max_length=50)
    filename: str = Field(default="document-draft", max_length=200)
    output_format: Literal["docx", "pdf", "txt"] = "docx"
