"""
Генерация текста юридического документа по запросу пользователя (GigaChat).
"""

from __future__ import annotations

import re

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

_SYSTEM_PROMPT = """Ты — помощник по подготовке черновиков юридических документов по законодательству РФ.

Задача: по запросу пользователя составить текст документа, готовый к правке юристом.

Правила:
1) Пиши на русском языке, официально-деловой стиль.
2) Не выдумывай конкретные нормы: если ссылаешься на закон — только общие формулировки или «ст. ___ ГК РФ» с пометкой проверить актуальную редакцию.
3) Если в запросе или контексте чата нет данных (ФИО, адреса, суммы, номер дела) — оставь понятные плейсхолдеры в квадратных скобках, например [ФИО истца], [АДРЕС], [СУММА].
4) Структура: шапка (кому/от кого), название документа, основная часть, просьба/требования, приложения (если уместно), дата и подпись.
5) Без Markdown (#, **, списков с -). Обычный текст, абзацы через пустую строку.
6) В конце отдельной строкой добавь: «Черновик сформирован ИИ. Требуется проверка юристом перед подачей.»
7) Не добавляй пояснений вне документа.

Формат ответа (строго):
TITLE: <краткое название документа, 3–80 символов>
---
<полный текст документа>
"""

_TITLE_BODY_RE = re.compile(
    r"^TITLE:\s*(.+?)\s*\n---\s*\n(.*)$",
    re.DOTALL | re.IGNORECASE,
)


def _parse_model_output(raw: str, *, fallback_title: str) -> tuple[str, str]:
    text = (raw or "").strip()
    if not text:
        raise ValueError("Модель вернула пустой ответ")

    match = _TITLE_BODY_RE.match(text)
    if match:
        title = match.group(1).strip().strip('"').strip("'")
        body = match.group(2).strip()
        if title and body:
            return title[:200], body

    lines = text.splitlines()
    if lines and len(lines[0]) < 120 and not lines[0].startswith("В "):
        title = lines[0].strip().strip("#").strip()
        body = "\n".join(lines[1:]).strip() or text
        return title[:200], body

    return fallback_title[:200], text


async def generate_ai_document_text(
    user_prompt: str,
    *,
    context_text: str = "",
    document_type_hint: str | None = None,
    title_hint: str | None = None,
) -> tuple[str, str]:
    if not settings.GIGACHAT_CLIENT_ID or not settings.GIGACHAT_CLIENT_SECRET:
        raise RuntimeError("GigaChat не настроен: укажите GIGACHAT_CLIENT_ID и GIGACHAT_CLIENT_SECRET")

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
    return _parse_model_output(raw, fallback_title=fallback or "Юридический документ")
