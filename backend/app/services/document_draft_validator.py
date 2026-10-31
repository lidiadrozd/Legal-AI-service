from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from app.schemas.document_draft import DocumentDraftResponse, DocumentClarificationResponse
from app.core.prompts import LEGAL_SCOPE_REFUSAL

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
    normalized = re.sub(r"\b(?:такой|такую|этот|эту|аналогичный|аналогичную)\s+", "", normalized)
    # Discussing a contract or an employer's request to sign one is ordinary advice.
    # A drafting request needs an action, rather than a document noun alone.
    if re.search(r"\b(?:как|зачем|почему)\s+(?:мне\s+)?(?:составить|оформить|подготовить|написать|создать|сформировать)\b", normalized):
        return False
    if re.search(r"\b(?:требует|просит|заставляет)\s+(?:меня\s+)?(?:составить|оформить|подготовить|написать|создать|сформировать)\b", normalized):
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


DOCUMENT_FORMAT_RETRY = (
    "Предыдущий ответ не прошёл проверку JSON документа. Верни тот же документ "
    "ровно одним валидным JSON-объектом по схеме из системных правил. "
    "Не меняй известные факты и не добавляй новые; неизвестные данные оставь "
    "явными заполнителями только для согласованного образца. Если существенных фактов "
    "недостаточно, верни JSON с status=needs_clarification и questions по системным правилам, "
    "не создавай документ. Экранируй переносы строк и кавычки внутри строк. "
    "Без Markdown и пояснений вне JSON."
)


def is_valid_document_response(response_text: str) -> bool:
    payload = extract_json_object(response_text)
    if payload is None:
        return False
    try:
        if payload.get("status") == "needs_clarification":
            DocumentClarificationResponse.model_validate(payload)
        else:
            validate_document_draft_payload(payload)
    except ValidationError:
        return False
    return True


CLARIFICATION_PREFIX = "Для подготовки документа не хватает данных."


def format_document_clarification(clarification: DocumentClarificationResponse) -> str:
    return CLARIFICATION_PREFIX + "\n" + "\n".join(
        question for question in clarification.questions[:1]
    )


def has_pending_document_clarification(chat_history: str) -> bool:
    replies = re.split(r"(?:^|\n)assistant:\s*", chat_history or "")
    return len(replies) > 1 and replies[-1].startswith(CLARIFICATION_PREFIX)


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

    if response_text.strip() == LEGAL_SCOPE_REFUSAL:
        return LEGAL_SCOPE_REFUSAL

    payload = extract_json_object(response_text)
    if payload is None:
        return (
            "Не удалось оформить документ: ответ модели не содержит валидный JSON. "
            "Повторите запрос и укажите недостающие факты (стороны, суд, даты, приложения)."
        )

    try:
        if payload.get("status") == "needs_clarification":
            return format_document_clarification(DocumentClarificationResponse.model_validate(payload))
        draft = validate_document_draft_payload(payload)
    except ValidationError as exc:
        details = "; ".join(error["msg"] for error in exc.errors())
        return (
            "Не удалось оформить документ: структура JSON не прошла проверку. "
            f"{details}"
        )

    return format_document_draft_for_user(draft)
