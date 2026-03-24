"""
Law Monitor Service — парсинг RSS лент и категоризация изменений законодательства.
Кэширование через Redis (TTL 1 час).
"""
from dotenv import load_dotenv
load_dotenv(".env")
import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

import aiohttp
import feedparser
import redis.asyncio as aioredis
from thefuzz import fuzz

from app.core.config import settings

logger = logging.getLogger(__name__)

# RSS ИСТОЧНИКИ (бесплатные, без ключей)
RSS_SOURCES = {
    "pravo_gov": "http://publication.pravo.gov.ru/api/rss?pageSize=200",
    "consultant": "https://www.consultant.ru/rss/hotdocs.xml",
}

# СЛОВАРЬ КЛЮЧЕВЫХ СЛОВ ПО КАТЕГОРИЯМ
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "civil_law": [
        "гражданский кодекс", "гк рф", "договор", "сделка", "обязательство",
        "собственность", "аренда", "купля-продажа", "наследство", "залог",
        "поручительство", "возмещение ущерба", "неустойка",
    ],
    "criminal_law": [
        "уголовный кодекс", "ук рф", "преступление", "наказание", "штраф",
        "лишение свободы", "судимость", "амнистия", "условный срок",
        "уголовная ответственность", "следствие",
    ],
    "labor_law": [
        "трудовой кодекс", "тк рф", "трудовой договор", "увольнение",
        "зарплата", "отпуск", "больничный", "охрана труда", "работодатель",
        "работник", "сокращение", "пособие", "мрот",
    ],
    "tax_law": [
        "налоговый кодекс", "нк рф", "налог", "ндс", "ндфл", "налоговая",
        "фнс", "декларация", "вычет", "акциз", "налогообложение",
        "налоговая проверка", "недоимка",
    ],
    "administrative_law": [
        "коап", "административный кодекс", "административный штраф",
        "протокол", "постановление", "проверка", "лицензия",
        "административное правонарушение", "роспотребнадзор",
    ],
    "housing_law": [
        "жилищный кодекс", "жк рф", "жкх", "квартира", "коммунальные услуги",
        "управляющая компания", "капитальный ремонт", "найм",
        "приватизация", "расселение", "снос",
    ],
    "family_law": [
        "семейный кодекс", "ск рф", "развод", "алименты", "опека",
        "усыновление", "брак", "раздел имущества", "попечительство",
        "материнский капитал",
    ],
    "corporate_law": [
        "акционерное общество", "ооо", "ао", "пао", "устав", "акции",
        "дивиденды", "банкротство", "ликвидация", "реорганизация",
        "корпоративный", "генеральный директор",
    ],
}

FALLBACK_CATEGORY = "other"
FUZZY_THRESHOLD = 75  # минимальный % совпадения для fuzzy matching

REDIS_CACHE_TTL = 3600  # 1 час в секундах
REDIS_KEY_PREFIX = "law_monitor:"

# СЕРВИС

class LawMonitorService:
    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = await aioredis.from_url( # type: ignore
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    # КЭШИРОВАНИЕ
    async def _cache_get(self, key: str) -> Optional[list[dict]]:
        """Читаем из Redis. Возвращает список статей или None."""
        try:
            redis = await self._get_redis()
            raw = await redis.get(f"{REDIS_KEY_PREFIX}{key}")
            if raw:
                logger.debug(f"Cache HIT: {key}")
                return json.loads(raw)
        except Exception as e:
            logger.warning(f"Redis get error ({key}): {e}")
        return None

    async def _cache_set(self, key: str, data: list[dict]) -> None:
        """Сохраняем в Redis с TTL 1 час."""
        try:
            redis = await self._get_redis()
            await redis.setex(
                f"{REDIS_KEY_PREFIX}{key}",
                REDIS_CACHE_TTL,
                json.dumps(data, ensure_ascii=False),
            )
            logger.debug(f"Cache SET: {key} (TTL={REDIS_CACHE_TTL}s)")
        except Exception as e:
            logger.warning(f"Redis set error ({key}): {e}")

    # ПАРСИНГ ОДНОГО RSS ИСТОЧНИКА
    async def _fetch_rss(self, session: aiohttp.ClientSession, name: str, url: str) -> list[dict]:

        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                response.raise_for_status()
                content = await response.text()

            feed = feedparser.parse(content)

            articles = []
            for entry in feed.entries:
                articles.append({
                    "source": name,
                    "title": entry.get("title", ""),
                    "summary": entry.get("summary", ""),
                    "link": entry.get("link", ""),
                    "published": entry.get("published", ""),
                })

            logger.info(f"[{name}] Получено {len(articles)} записей")
            return articles

        except aiohttp.ClientConnectionError as e:
            logger.error(f"[{name}] Ошибка подключения: {e}")
        except aiohttp.ClientResponseError as e:
            logger.error(f"[{name}] HTTP ошибка {e.status}: {e.message}")
        except asyncio.TimeoutError:
            logger.error(f"[{name}] Таймаут при подключении к {url}")
        except Exception as e:
            logger.error(f"[{name}] Непредвиденная ошибка: {e}")

        return []

    # КАТЕГОРИЗАЦИЯ ОДНОЙ СТАТЬИ
    @staticmethod
    def _categorize(title: str, summary: str) -> str:

        text = f"{title} {summary}".lower()

        best_category = FALLBACK_CATEGORY
        best_score = 0

        for category, keywords in CATEGORY_KEYWORDS.items():
            for keyword in keywords:
                # Шаг 1: точное вхождение
                if keyword in text:
                    return category

                # Шаг 2: fuzzy matching
                score = fuzz.partial_ratio(keyword, text)
                if score > best_score:
                    best_score = score
                    best_category = category

        if best_score >= FUZZY_THRESHOLD:
            return best_category

        return FALLBACK_CATEGORY

    # ПАРСИНГ ГОСУДАРСТВЕННОЙ ДУМЫ
    async def _fetch_duma(self, session: aiohttp.ClientSession) -> list[dict]:
        api_key = getattr(settings, "DUMA_API_KEY", None)
        app_key = getattr(settings, "DUMA_APP_KEY", None)

        if not api_key or not app_key:
            logger.debug("[duma] Ключи не заданы, пропускаем")
            return []

        url = f"http://api.duma.gov.ru/api/{api_key}/search.json"
        params = {
            "app_token": app_key,
            "limit": 20,
            "sort": "date",
        }

        try:
            async with session.get(
                url, params=params,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                response.raise_for_status()
                data = await response.json()

            articles = []
            for law in data.get("laws", []):
                articles.append({
                    "source": "duma",
                    "title": law.get("name", ""),
                    "summary": law.get("comments", ""),
                    "link": f"http://sozd.duma.gov.ru/bill/{law.get('number', '')}",
                    "published": law.get("date", ""),
                })

            logger.info(f"[duma] Получено {len(articles)} законопроектов")
            return articles

        except aiohttp.ClientResponseError as e:
            logger.error(f"[duma] HTTP ошибка {e.status}: {e.message}")
        except asyncio.TimeoutError:
            logger.error("[duma] Таймаут")
        except Exception as e:
            logger.error(f"[duma] Ошибка: {e}")

        return []

    # ОСНОВНОЙ ПУБЛИЧНЫЙ МЕТОД
    async def get_law_updates(self, use_cache: bool = True) -> list[dict]:

        cache_key = "all_updates"

        if use_cache:
            cached = await self._cache_get(cache_key)
            if cached is not None:
                return cached

        # Параллельный fetch всех источников (RSS + Дума)
        async with aiohttp.ClientSession() as session:
            tasks = [
                self._fetch_rss(session, name, url)
                for name, url in RSS_SOURCES.items()
            ]
            tasks.append(self._fetch_duma(session))
            results = await asyncio.gather(*tasks)

        # Объединяем и категоризируем
        all_articles: list[dict] = []
        for articles in results:
            for article in articles:
                article["category"] = self._categorize(
                    article["title"],
                    article["summary"],
                )
                article["fetched_at"] = datetime.utcnow().isoformat()
                all_articles.append(article)

        logger.info(f"Всего статей: {len(all_articles)}")

        # Сохраняем в кэш
        await self._cache_set(cache_key, all_articles)

        return all_articles

    async def get_updates_by_category(self, category: str) -> list[dict]:
        """Возвращает статьи только по заданной категории."""
        all_updates = await self.get_law_updates()
        return [a for a in all_updates if a["category"] == category]


# Синглтон (в стиле gigachat_client.py)
_law_monitor_service: Optional[LawMonitorService] = None

def get_law_monitor_service() -> LawMonitorService:
    global _law_monitor_service
    if _law_monitor_service is None:
        _law_monitor_service = LawMonitorService()
    return _law_monitor_service