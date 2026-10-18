from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.law_changes import LawChange, LawDocument
from app.models.user_law_interest import UserLawInterest
from app.models.user import User
from app.services.law_notification_service import (
    dispatch_law_change_notifications,
)


DEMO_TOPIC_KEY = "demo_zhkh"
DEMO_TOPIC_LABEL = "ЖКХ (демо)"
DEMO_KEYWORDS = ["жкх", "коммунальн", "управляющ"]

DEMO_LAWS = [
    {
        "number": "DEMO-ZHKH-2026-001",
        "title": "ДЕМО: Начисление платы за коммунальные услуги",
        "description": (
            "ТЕСТОВОЕ ИЗМЕНЕНИЕ. ЖКХ: демонстрационный порядок "
            "начисления платы за коммунальные услуги."
        ),
    },
    {
        "number": "DEMO-ZHKH-2026-002",
        "title": "ДЕМО: Требования к управляющим организациям",
        "description": (
            "ТЕСТОВОЕ ИЗМЕНЕНИЕ. ЖКХ: демонстрационные требования "
            "к управляющим организациям."
        ),
    },
    {
        "number": "DEMO-ZHKH-2026-003",
        "title": "ДЕМО: Отключение коммунальных услуг",
        "description": (
            "ТЕСТОВОЕ ИЗМЕНЕНИЕ. ЖКХ: информирование жильцов "
            "о плановых отключениях коммунальных услуг."
        ),
    },
]


async def run(email: str) -> None:
    async with AsyncSessionLocal() as db:
        # Находим существующего активного пользователя.
        user_result = await db.execute(
            select(User).where(
                User.email == email,
                User.is_active.is_(True),
            )
        )
        user = user_result.scalar_one_or_none()

        if user is None:
            raise RuntimeError(
                f"Активный пользователь {email!r} не найден."
            )

        # Создаём или обновляем интерес пользователя к ЖКХ.
        interest_result = await db.execute(
            select(UserLawInterest).where(
                UserLawInterest.user_id == user.id,
                UserLawInterest.chat_id.is_(None),
                UserLawInterest.topic_key == DEMO_TOPIC_KEY,
            )
        )
        interest = interest_result.scalar_one_or_none()

        if interest is None:
            interest = UserLawInterest(
                user_id=user.id,
                chat_id=None,
                topic_key=DEMO_TOPIC_KEY,
                topic_label=DEMO_TOPIC_LABEL,
                keywords=DEMO_KEYWORDS,
                source_excerpt="Демо-настройка интереса к теме ЖКХ",
            )
            db.add(interest)
        else:
            interest.topic_label = DEMO_TOPIC_LABEL
            interest.keywords = DEMO_KEYWORDS
            interest.source_excerpt = (
                "Демо-настройка интереса к теме ЖКХ"
            )

        change_ids: list[int] = []

        for item in DEMO_LAWS:
            # Ищем документ по уникальному номеру.
            document_result = await db.execute(
                select(LawDocument).where(
                    LawDocument.number == item["number"]
                )
            )
            document = document_result.scalar_one_or_none()

            if document is None:
                document = LawDocument(
                    number=item["number"],
                    title=item["title"],
                    full_text=item["description"],
                    source_url=None,
                    published_at=datetime.now(timezone.utc),
                    law_type="DEMO",
                    status="active",
                )
                db.add(document)
                await db.flush()
            else:
                document.title = item["title"]
                document.full_text = item["description"]

            # Ищем изменение, чтобы повторный запуск
            # не создавал новое изменение для того же демо-документа.
            change_result = await db.execute(
                select(LawChange).where(
                    LawChange.document_id == document.id,
                    LawChange.change_title == item["title"],
                )
            )
            change = change_result.scalar_one_or_none()

            if change is None:
                change = LawChange(
                    document_id=document.id,
                    change_title=item["title"],
                    change_date=datetime.now(timezone.utc),
                    diff={
                        "category": "ЖКХ",
                        "tags": ["ЖКХ"],
                        "demo": True,
                    },
                    description=item["description"],
                    source_url=None,
                )
                db.add(change)
                await db.flush()
            else:
                change.change_date = datetime.now(timezone.utc)
                change.diff = {
                    "category": "ЖКХ",
                    "tags": ["ЖКХ"],
                    "demo": True,
                }
                change.description = item["description"]

            change_ids.append(change.id)

        # Сохраняем документы, изменения и интерес пользователя.
        await db.commit()

        print(f"Пользователь: {user.email}, ID: {user.id}")
        print(f"Интерес: {DEMO_TOPIC_LABEL}")
        print(f"ID изменений: {change_ids}")

        # Передаём только созданные демонстрационные изменения.
        created_count = await dispatch_law_change_notifications(
            db,
            lookback_days=2,
            change_ids=change_ids,
        )

        print(f"Создано новых уведомлений: {created_count}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Создание демонстрационных уведомлений ЖКХ"
    )
    parser.add_argument(
        "--email",
        required=True,
        help="Email существующего активного пользователя",
    )
    args = parser.parse_args()

    asyncio.run(run(args.email))


if __name__ == "__main__":
    main()
