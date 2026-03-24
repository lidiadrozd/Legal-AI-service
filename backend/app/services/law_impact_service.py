"""
Law Impact Service — анализ влияния изменений законодательства на дела пользователей.
Использует GigaChat для оценки релевантности каждого изменения закона.
"""

import json
import logging
from typing import Optional

from langchain.schema import HumanMessage, SystemMessage
from langchain_gigachat import GigaChat

from app.core.prompts import get_law_impact_prompt
from app.services.gigachat_client import get_gigachat_client

logger = logging.getLogger(__name__)

# temperature=0.1 — минимальная случайность, максимальная точность для юридического анализа
GIGACHAT_MODEL = "GigaChat-Pro"
GIGACHAT_TEMPERATURE = 0.1


async def analyze_law_impact(
    case_category: str,
    case_description: str,
    change: dict,
) -> dict:
    """
    Анализирует влияние одного изменения закона на дело пользователя.

    Аргументы:
        case_category    — категория дела (например "tax_law", "labor_law")
        case_description — описание дела пользователя
        change           — словарь с данными об изменении (из law_monitor_service)

    Возвращает словарь:
        {
            "affects": true/false,
            "severity": "high/medium/low/none",
            "reason": "Краткое объяснение",
            "legal_basis": "ст. XX ГК РФ или null",
            "recommended_actions": ["действие 1", ...],
            "notification_template": "law_change_critical/law_change_standard/null",
            "urgency_days": 7/14/30/null
        }

    При ошибке возвращает fallback с affects=False.
    """
    prompt = get_law_impact_prompt(
        case_category=case_category,
        case_description=case_description,
        change_title=change.get("title", ""),
        change_category=change.get("category", "other"),
        change_summary=change.get("summary", ""),
        change_source=change.get("source", ""),
        change_date=change.get("published", ""),
    )

    try:
        client = await get_gigachat_client()

        llm = GigaChat(
            credentials=client.auth_header,
            model=GIGACHAT_MODEL,
            temperature=GIGACHAT_TEMPERATURE,
            verify_ssl_certs=False,
        )

        messages = [
            SystemMessage(content="Ты юридический аналитик. Отвечай ТОЛЬКО валидным JSON без пояснений."),
            HumanMessage(content=prompt),
        ]

        response = await llm.ainvoke(messages)
        raw = response.content

        # Чистим ответ от возможных markdown блоков (```json ... ```)
        clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        result = json.loads(clean)

        logger.info(
            f"[law_impact] {change.get('source')} | affects={result.get('affects')} "
            f"severity={result.get('severity')} | {case_category}"
        )
        return result

    except json.JSONDecodeError as e:
        logger.error(f"[law_impact] Ошибка парсинга JSON от GigaChat: {e} | raw={raw[:200]}")
    except Exception as e:
        logger.error(f"[law_impact] Ошибка анализа: {e}")

    # Fallback — если что-то пошло не так, считаем что не влияет
    return {
        "affects": False,
        "severity": "none",
        "reason": "Ошибка анализа",
        "legal_basis": None,
        "recommended_actions": [],
        "notification_template": None,
        "urgency_days": None,
    }


async def analyze_changes_for_case(
    case_category: str,
    case_description: str,
    changes: list[dict],
) -> list[dict]:
    """
    Анализирует список изменений законов для одного дела.
    Возвращает только те изменения которые влияют на дело (affects=True).

    Аргументы:
        case_category    — категория дела
        case_description — описание дела
        changes          — список изменений из law_monitor_service.get_law_updates()

    Возвращает список словарей:
        [
            {
                "change": {...},   # оригинальные данные изменения
                "analysis": {...}  # результат analyze_law_impact()
            },
            ...
        ]
    """
    relevant = []

    for change in changes:
        analysis = await analyze_law_impact(
            case_category=case_category,
            case_description=case_description,
            change=change,
        )

        if analysis.get("affects"):
            relevant.append({
                "change": change,
                "analysis": analysis,
            })

    logger.info(
        f"[law_impact] Дело '{case_category}': "
        f"{len(relevant)}/{len(changes)} изменений релевантны"
    )
    return relevant