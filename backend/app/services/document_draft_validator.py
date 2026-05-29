from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from app.schemas.document_draft import DocumentDraftResponse

DOCUMENT_REQUEST_KEYWORDS = (
    "документ",
    "претенз",
    "исков",
    "иск ",
    "ходатайств",
    "договор",
    "заявлен",
    "жалоб",
    "составь",
    "сформируй",
    "оформи",
    "подготовь",
    "черновик",
)

REQUISITE_LABELS = {
    "document_type": "Вид документа",
    "court": "Суд",
    "plaintiff": "Истец / заявитель",
    "defendant": "Ответчик / адресат",
    "plaintiff_address": "Адрес истца / заявителя",
    "defendant_address": "Адрес ответчика / адресата",
    "case_number": "Номер дела",
    "document_date": "Дата",
    "attachments": "Приложения",
    "signature": "Подпись",
}


def is_document_generation_request(user_query: str) -> bool:
    normalized = (user_query or "").lower()
    return any(keyword in normalized for keyword in DOCUMENT_REQUEST_KEYWORDS)


def extract_json_object(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        raw = fenced.group(1).strip()
    elif not raw.startswith("{"):
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        raw = raw[start : end + 1]

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def validate_document_draft_payload(payload: dict[str, Any]) -> DocumentDraftResponse:
    return DocumentDraftResponse.model_validate(payload)


def format_document_draft_for_user(draft: DocumentDraftResponse) -> str:
    lines = [draft.title.strip(), "", draft.text.strip(), "", "Реквизиты:"]
    requisites = draft.requisites.model_dump(exclude_none=True)
    for key, value in requisites.items():
        label = REQUISITE_LABELS.get(key, key.replace("_", " "))
        if isinstance(value, list):
            rendered = "; ".join(value)
        else:
            rendered = str(value)
        lines.append(f"- {label}: {rendered}")
    return "\n".join(lines).strip()


def process_document_response(user_query: str, response_text: str) -> str:
    if not is_document_generation_request(user_query):
        return response_text

    payload = extract_json_object(response_text)
    if payload is None:
        return (
            "Не удалось оформить документ: ответ модели не содержит валидный JSON. "
            "Повторите запрос и укажите недостающие факты (стороны, суд, даты, приложения)."
        )

    try:
        draft = validate_document_draft_payload(payload)
    except ValidationError as exc:
        details = "; ".join(error["msg"] for error in exc.errors())
        return (
            "Не удалось оформить документ: структура JSON не прошла проверку. "
            f"{details}"
        )

    return format_document_draft_for_user(draft)
