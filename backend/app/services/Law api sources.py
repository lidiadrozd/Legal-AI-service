"""
Заготовки для подключения пока не полученных источников законодательства.
"""

import asyncio
import logging
from typing import Optional
import aiohttp

logger = logging.getLogger(__name__)


# 1. ГАРАНТ
GARANT_CATEGORY_IDS = [1, 2, 3, 4, 5]  # уточнить после получения доступа

async def fetch_garant(session: aiohttp.ClientSession, api_key: str) -> list[dict]:

    from datetime import date, timedelta

    url = "https://api.garant.ru/v1/prime/create-news"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-type": "application/json",
    }
    # Берём документы за последние сутки
    from_date = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    payload = {
        "fromDate": from_date,
        "categories": GARANT_CATEGORY_IDS,
    }

    try:
        async with session.post(
            url, headers=headers, json=payload,
            timeout=aiohttp.ClientTimeout(total=10)
        ) as response:
            response.raise_for_status()
            data = await response.json()

        articles = []
        base_url = "https://internet.garant.ru"
        for item in data.get("news", []):
            doc = item.get("document", {})
            articles.append({
                "source": "garant",
                "title": item.get("name", ""),
                # paragraphs — список абзацев, объединяем в summary
                "summary": " ".join(item.get("paragraphs", [])),
                "link": f"{base_url}{doc.get('url', '')}",
                "published": from_date,
            })

        logger.info(f"[garant] Получено {len(articles)} документов")
        return articles

    except aiohttp.ClientResponseError as e:
        logger.error(f"[garant] HTTP ошибка {e.status}: {e.message}")
    except Exception as e:
        logger.error(f"[garant] Ошибка: {e}")

    return []

# 2. ФНС

async def fetch_fns(session: aiohttp.ClientSession, api_key: str) -> list[dict]:
    """
    Получение новостей и изменений от ФНС через API.
    """
    url = "https://api-fns.ru/api/news"
    params = {
        "key": api_key,
        "limit": 20,
    }

    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
            response.raise_for_status()
            data = await response.json()

        articles = []
        for item in data.get("items", []):
            articles.append({
                "source": "fns",
                "title": item.get("title", ""),
                "summary": item.get("description", ""),
                "link": item.get("link", ""),
                "published": item.get("pubDate", ""),
            })

        logger.info(f"[fns] Получено {len(articles)} новостей")
        return articles

    except aiohttp.ClientResponseError as e:
        logger.error(f"[fns] HTTP ошибка {e.status}: {e.message}")
    except Exception as e:
        logger.error(f"[fns] Ошибка: {e}")

    return []