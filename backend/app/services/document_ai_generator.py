"""
Генерация текста юридического документа по запросу пользователя (GigaChat).
"""

from __future__ import annotations

import json

from app.core.prompts import DOCUMENT_JSON_RULES, LEGAL_SCOPE_RULES, LEGAL_SCOPE_REFUSAL, DOCUMENT_DRAFT_FUNCTION
from app.schemas.document_draft import DocumentDraftResponse
from pydantic import ValidationError
from app.services.document_draft_validator import DOCUMENT_FORMAT_RETRY

from app.core.config import settings
from app.services.gigachat_client import get_gigachat_client

_DOCUMENT_TYPE_HINTS: dict[str, str] = {
    "claim": "исковое заявление",
    "pretense": "досудебная претензия",
    "complaint": "жалоба",
    "contract": "договор",
    "motion": "ходатайство",
    "appeal": "апелляционная жалоба",
    "power_of_attorney": "доверенность",
    "other": "иной процессуальный или гражданско-правовой документ",
}

_SYSTEM_PROMPT = (
    "Ты — помощник по подготовке черновиков юридических документов по законодательству РФ. "
    "Пиши на русском языке в официально-деловом стиле. Не задавай повторных вопросов; используй факты из контекста.\n"
    + LEGAL_SCOPE_RULES + DOCUMENT_JSON_RULES
    + "\nВ конце поля «текст» добавь: «Черновик сформирован ИИ. Требуется проверка юристом перед подачей.»"
)


def _parse_model_output(raw: str, *, fallback_title: str) -> tuple[str, str]:
    # Keep the existing caller interface; a malformed answer is never a document.
    text = (raw or "").strip()
    if text == LEGAL_SCOPE_REFUSAL:
        raise ValueError(LEGAL_SCOPE_REFUSAL)
    try:
        draft = DocumentDraftResponse.model_validate(json.loads(text))
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise ValueError("Модель вернула некорректный JSON документа. Повторите запрос.") from exc
    return draft.title.strip()[:200], draft.text.strip()


async def generate_ai_document_text(
    user_prompt: str,
    *,
    context_text: str = "",
    document_type_hint: str | None = None,
    title_hint: str | None = None,
) -> tuple[str, str]:
    prompt = user_prompt.strip()
    if len(prompt) < 10:
        raise ValueError("Опишите запрос подробнее (минимум 10 символов)")

    type_label = _DOCUMENT_TYPE_HINTS.get(document_type_hint or "", "")
    user_parts = [f"Запрос пользователя:\n{prompt}"]
    if type_label:
        user_parts.append(f"Тип документа (ориентир): {type_label}")
    if title_hint and title_hint.strip():
        user_parts.append(f"Желаемое название: {title_hint.strip()}")
    if context_text.strip():
        user_parts.append(
            "Контекст из переписки (используй факты, не повторяй вопросы):\n"
            + context_text.strip()[-12000:]
        )

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]

    client = await get_gigachat_client()
    raw = await client.chat_completion(
        messages,
        model=settings.GIGACHAT_MODEL,
        temperature=0.15,
    )

    fallback = (title_hint or type_label or "Юридический документ").strip()
    try:
        return _parse_model_output(raw.content, fallback_title=fallback or "Юридический документ")
    except ValueError:
        if raw.content.strip() == LEGAL_SCOPE_REFUSAL:
            raise
    repaired = await client.chat_completion(
        messages + [
            {"role": "assistant", "content": raw.content},
            {"role": "user", "content": DOCUMENT_FORMAT_RETRY},
        ], model=settings.GIGACHAT_MODEL, temperature=0.0,
        structured_function=DOCUMENT_DRAFT_FUNCTION,
    )
    return _parse_model_output(repaired.content, fallback_title=fallback or "Юридический документ")
