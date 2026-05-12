from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.law_changes import LawChange
from app.models.user_law_interest import UserLawInterest

TOPIC_DEFINITIONS: dict[str, dict[str, object]] = {
    "housing_rental": {
        "label": "Аренда и найм жилья",
        "keywords": [
            "аренд",
            "найм",
            "квартир",
            "жил",
            "жк рф",
            "жилищн",
            "наймодат",
            "арендодат",
            "договор найма",
        ],
    },
    "employment": {
        "label": "Трудовые отношения",
        "keywords": ["труд", "увольн", "зарплат", "работодат", "сотрудник", "тк рф", "отпуск"],
    },
    "consumer_rights": {
        "label": "Защита прав потребителей",
        "keywords": ["потребител", "возврат", "зозпп", "гарант", "магазин", "услуг"],
    },
    "tax": {
        "label": "Налоги",
        "keywords": ["налог", "ндс", "ндфл", "фнс", "налогов", "нк рф"],
    },
    "family_law": {
        "label": "Семейное право",
        "keywords": ["развод", "алим", "брак", "семейн", "ск рф", "ребен"],
    },
    "civil_contracts": {
        "label": "Гражданские договоры",
        "keywords": ["договор", "гк рф", "обязательств", "подряд", "поставк", "купл", "продаж"],
    },
    "agriculture": {
        "label": "Сельское хозяйство",
        "keywords": ["сельск", "агро", "ферм", "урож", "минсельхоз"],
    },
    "bankruptcy": {
        "label": "Банкротство",
        "keywords": ["банкрот", "несостоятель", "127-фз"],
    },
    "personal_data": {
        "label": "Персональные данные",
        "keywords": ["персональн", "152-фз", "пдн", "обработк данных"],
    },
    "court_procedure": {
        "label": "Судебное производство",
        "keywords": ["иск", "суд", "апелляц", "кассац", "процессуальн", "апк", "гпк"],
    },
}


@dataclass(frozen=True)
class ExtractedTopic:
    topic_key: str
    topic_label: str
    keywords: tuple[str, ...]


def extract_topics_from_text(text: str) -> list[ExtractedTopic]:
    normalized = (text or "").lower()
    if not normalized.strip():
        return []

    found: list[ExtractedTopic] = []
    for topic_key, definition in TOPIC_DEFINITIONS.items():
        raw_keywords = definition.get("keywords") or []
        matched = [keyword for keyword in raw_keywords if keyword in normalized]
        if not matched:
            continue
        found.append(
            ExtractedTopic(
                topic_key=topic_key,
                topic_label=str(definition.get("label") or topic_key),
                keywords=tuple(str(keyword) for keyword in raw_keywords),
            )
        )
    return found


def build_change_search_text(*, title: str | None, description: str | None, category: str | None = None) -> str:
    parts = [title or "", description or "", category or ""]
    return " ".join(part.strip() for part in parts if part and part.strip()).lower()


def change_matches_interest(change_text: str, keywords: list[str] | tuple[str, ...]) -> bool:
    normalized = (change_text or "").lower()
    if not normalized:
        return False
    return any(keyword.lower() in normalized for keyword in keywords if keyword)


async def sync_user_interests_from_message(
    db: AsyncSession,
    *,
    user_id: int,
    chat_id: int,
    text: str,
) -> list[UserLawInterest]:
    topics = extract_topics_from_text(text)
    if not topics:
        return []

    excerpt = (text or "").strip()[:500]
    saved: list[UserLawInterest] = []
    for topic in topics:
        result = await db.execute(
            select(UserLawInterest).where(
                UserLawInterest.user_id == user_id,
                UserLawInterest.chat_id == chat_id,
                UserLawInterest.topic_key == topic.topic_key,
            )
        )
        interest = result.scalar_one_or_none()
        if interest is None:
            interest = UserLawInterest(
                user_id=user_id,
                chat_id=chat_id,
                topic_key=topic.topic_key,
                topic_label=topic.topic_label,
                keywords=list(topic.keywords),
                source_excerpt=excerpt,
            )
            db.add(interest)
        else:
            merged_keywords = list(dict.fromkeys([*interest.keywords, *topic.keywords]))
            interest.keywords = merged_keywords
            interest.topic_label = topic.topic_label
            interest.source_excerpt = excerpt
        saved.append(interest)

    await db.commit()
    for item in saved:
        await db.refresh(item)
    return saved


async def get_relevant_law_changes_for_user(
    db: AsyncSession,
    *,
    user_id: int,
    chat_id: int | None = None,
    limit: int = 3,
) -> list[LawChange]:
    query = select(UserLawInterest).where(UserLawInterest.user_id == user_id)
    if chat_id is not None:
        query = query.where(UserLawInterest.chat_id == chat_id)
    interests_result = await db.execute(query)
    interests = list(interests_result.scalars().all())
    if not interests:
        return []

    changes_result = await db.execute(select(LawChange).order_by(LawChange.created_at.desc()).limit(100))
    changes = list(changes_result.scalars().all())
    matched: list[LawChange] = []
    for change in changes:
        category = change.diff.get("category") if isinstance(change.diff, dict) else None
        change_text = build_change_search_text(
            title=change.change_title,
            description=change.description,
            category=category,
        )
        if any(change_matches_interest(change_text, interest.keywords) for interest in interests):
            matched.append(change)
        if len(matched) >= limit:
            break
    return matched
