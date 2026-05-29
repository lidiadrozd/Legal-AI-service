from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DocumentRequisites(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    document_type: str | None = Field(default=None, alias="вид_документа")
    court: str | None = Field(default=None, alias="суд")
    plaintiff: str | None = Field(default=None, alias="истец")
    defendant: str | None = Field(default=None, alias="ответчик")
    plaintiff_address: str | None = Field(default=None, alias="адрес_истца")
    defendant_address: str | None = Field(default=None, alias="адрес_ответчика")
    case_number: str | None = Field(default=None, alias="номер_дела")
    document_date: str | None = Field(default=None, alias="дата")
    attachments: list[str] | str | None = Field(default=None, alias="приложения")
    signature: str | None = Field(default=None, alias="подпись")

    @field_validator("attachments", mode="before")
    @classmethod
    def normalize_attachments(cls, value: Any) -> list[str] | str | None:
        if value is None:
            return None
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return str(value).strip()

    @model_validator(mode="after")
    def require_minimum_legal_fields(self) -> "DocumentRequisites":
        filled = [
            value
            for value in (
                self.document_type,
                self.court,
                self.plaintiff,
                self.defendant,
                self.plaintiff_address,
                self.defendant_address,
                self.case_number,
                self.document_date,
                self.attachments,
                self.signature,
            )
            if value not in (None, "", [])
        ]
        if len(filled) < 2:
            raise ValueError(
                "В реквизитах должно быть минимум два заполненных юридических поля "
                "(суд, стороны, адреса, дата, приложения и т.д.)."
            )
        return self


class DocumentDraftResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    title: str = Field(alias="заголовок", min_length=3, max_length=500)
    text: str = Field(alias="текст", min_length=20)
    requisites: DocumentRequisites = Field(alias="реквизиты")
