from pydantic import BaseModel, Field


class TranscribeResponse(BaseModel):
    text: str = Field(..., description="Распознанный текст")
    language: str = "ru-RU"
