from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class StartDocumentInterview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(min_length=10, max_length=20000)
    chat_id: int | None = None
    title: str = Field(default="", max_length=200)
    document_type: str = Field(default="", max_length=50)
    filename: str = Field(default="document-draft", max_length=200)
    output_format: Literal["docx", "pdf", "txt"] = "docx"
