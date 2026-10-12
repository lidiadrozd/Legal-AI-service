from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from app.schemas.document_draft import DocumentDraftResponse

DOCUMENT_KIND_RE = re.compile(r"\b(?:документ\w*|претенз\w*|исков\w*|иск|ходатайств\w*|договор\w*|заявлен\w*|жалоб\w*)", re.I)
DOCUMENT_ACTION_RE = re.compile(r"\b(?:составь(?:те)?|составить|сформируй(?:те)?|сформировать|оформи(?:те)?|оформить|подготовь(?:те)?|подготовить|напиши(?:те)?|написать|создай(?:те)?|создать)\s+(?:мне\s+)?(?:пожалуйста[, ]+)?(?:проект\s+|черновик\s+|текст\s+)?(?:юридическ\w*\s+|исков\w*\s+)?(?:документ\w*|претенз\w*|иск\w*|ходатайств\w*|договор\w*|заявлен\w*|жалоб\w*)", re.I)


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
    # Discussing a contract or an employer's request to sign one is ordinary advice.
    # A drafting request needs an action, rather than a document noun alone.
    if re.search(r"\b(?:как|зачем|почему)\s+(?:мне\s+)?(?:составить|оформить|подготовить|написать)\b", normalized):
        return False
    if re.search(r"\b(?:требует|просит|заставляет)\s+(?:меня\s+)?(?:составить|оформить|подготовить|написать)\b", normalized):
        return False
    return bool(DOCUMENT_ACTION_RE.search(normalized) or
                (re.search(r"\b(?:нужен|нужна|нужно)\s+(?:мне\s+)?(?:черновик|образец|шаблон|текст)\b", normalized) and DOCUMENT_KIND_RE.search(normalized)))


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
