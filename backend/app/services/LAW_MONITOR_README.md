# Law Monitor Service

Сервис для мониторинга изменений законодательства: парсит RSS ленты и API источников, категоризирует документы, кэширует результаты в Redis.

---

## Файлы

| Файл | Описание                                           |
|------|----------------------------------------------------|
| `backend/app/services/law_monitor_service.py` | Основной сервис (RSS + Дума + категоризация + кэш) |
| `backend/app/services/law_api_sources.py` | Заготовки для будущих источников (Гарант, ФНС)     |

---

## Для бэкенда

### Как подключить сервис

```python
from app.services.law_monitor_service import get_law_monitor_service

service = get_law_monitor_service()
```

### Получить все обновления

```python
# Из кэша (Redis, TTL 1 час) — быстро
articles = await service.get_law_updates()

# Принудительное обновление (игнорирует кэш)
articles = await service.get_law_updates(use_cache=False)
```

### Получить обновления по категории

```python
articles = await service.get_updates_by_category("tax_law")
```

### Структура одной записи

```json
{
    "source": "consultant",
    "title": "Федеральный закон от ...",
    "summary": "Краткое описание",
    "link": "https://...",
    "published": "Mon, 20 Mar 2026 ...",
    "category": "tax_law",
    "fetched_at": "2026-03-20T10:00:00"
}
```

### Доступные категории

| Категория | Описание |
|-----------|----------|
| `civil_law` | Гражданское право (ГК РФ) |
| `criminal_law` | Уголовное право (УК РФ) |
| `labor_law` | Трудовое право (ТК РФ) |
| `tax_law` | Налоговое право (НК РФ) |
| `administrative_law` | Административное право (КоАП) |
| `housing_law` | Жилищное право (ЖК РФ) |
| `family_law` | Семейное право (СК РФ) |
| `corporate_law` | Корпоративное право |
| `other` | Не удалось определить категорию |

### Пример FastAPI эндпоинта

```python
from fastapi import APIRouter
from app.services.law_monitor_service import get_law_monitor_service

router = APIRouter()

@router.get("/law-updates")
async def get_updates(category: str = None):
    service = get_law_monitor_service()
    if category:
        return await service.get_updates_by_category(category)
    return await service.get_law_updates()
```

---

## Для фронтенда

### GET /law-updates

Возвращает список всех актуальных изменений законодательства.

**Параметры:**
- `category` (опционально) — фильтр по категории, например `tax_law`

**Пример запроса:**
```
GET /api/v1/law-updates
GET /api/v1/law-updates?category=tax_law
```

**Пример ответа:**
```json
[
  {
    "source": "consultant",
    "title": "Федеральный закон № 123-ФЗ ...",
    "summary": "О внесении изменений в НК РФ...",
    "link": "https://consultant.ru/...",
    "published": "Mon, 20 Mar 2026 09:00:00",
    "category": "tax_law",
    "fetched_at": "2026-03-20T10:00:00"
  }
]
```

**Поле `source`** — откуда пришла новость:
- `consultant` — КонсультантПлюс
- `pravo_gov` — Официальный портал правовой информации
- `duma` — Государственная Дума

---

## Для DevOps

### Переменные окружения (.env)

```env
# Redis — обязателен для кэширования (TTL 1 час)
REDIS_URL=redis://redis:6379/0

# Государственная Дума — оба ключа обязательны
DUMA_API_KEY=ваш_api_ключ
DUMA_APP_KEY=ваш_app_ключ

# Гарант — когда получим подписку
GARANT_API_KEY=ваш_ключ

# ФНС — когда получим ключ
FNS_API_KEY=ваш_ключ
```

### Без Redis

Сервис работает и без Redis — просто без кэша. При каждом запросе будет заново парсить все источники. В логах появится предупреждение:
```
Redis set error (all_updates): ...
```
Это не критично для разработки, но в проде Redis обязателен.

---

## Для Data Manager

### Текущие источники

| Источник | Статус | Тип | Ключ нужен |
|----------|--------|-----|------------|
| КонсультантПлюс | ✅ Работает | RSS | Нет |
| pravo.gov.ru | ✅ Работает | RSS | Нет |
| Государственная Дума | ✅ Работает | API | Да (есть) |
| Гарант | ⏳ Ожидает ключ | API | Да (нет) |
| ФНС | ⏳ Ожидает ключ | API | Да (нет) |

### Как добавить новый RSS источник

Открыть `law_monitor_service.py` и добавить в словарь `RSS_SOURCES`:

```python
RSS_SOURCES = {
    "pravo_gov": "http://publication.pravo.gov.ru/api/rss?pageSize=200",
    "consultant": "https://www.consultant.ru/rss/hotdocs.xml",
    "новый_источник": "https://ссылка/на/rss",  # добавить сюда
}
```

### Как добавить новый API источник

1. Написать функцию в `law_api_sources.py` по аналогии с `fetch_garant` или `fetch_duma`
2. Добавить метод в класс `LawMonitorService` в `law_monitor_service.py`
3. Добавить вызов в метод `get_law_updates`
4. Добавить ключ в `.env` и `config.py`
