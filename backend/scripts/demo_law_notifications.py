from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.chat import ChatSession
from app.models.law_changes import LawChange, LawDocument
from app.models.user_law_interest import UserLawInterest
from app.models.user import User
from app.models.law_reference_assessment import LawChangeDelivery
from app.models.notification import Notification

from app.services.law_notification_service import (
    dispatch_law_change_notifications,
)


TOPIC_KEY = "housing_utilities"
TOPIC_LABEL = "ЖКХ"

TOPIC_KEYWORDS = [
    "жкх",
    "коммунальн",
    "управляющ",
    "водоснабж",
    "отоплен",
    "электроснабж",
]

LAW_CHANGES = [
    {
        "number": "ZHKH-2026-001",
        "title": "ДЕМО: Порядок начисления платы за коммунальные услуги",
        "description": (
            "Изменение порядка расчета платы за коммунальные услуги. "
            "В рамках рассматриваемого изменения устанавливаются правила "
            "определения размера платы за холодное и горячее водоснабжение, "
            "водоотведение и отопление. "
            "При расчете учитываются показания индивидуальных и общедомовых "
            "приборов учета, нормативы потребления и период предоставления "
            "коммунальной услуги. "
            "Отдельно определяется порядок перерасчета платы при "
            "предоставлении услуги ненадлежащего качества."
        ),
    },
    {
        "number": "ZHKH-2026-002",
        "title": "ДЕМО: Требования к деятельности управляющих организаций",
        "description": (
            "Изменение требований к деятельности управляющих организаций "
            "в сфере управления многоквартирными домами. "
            "Устанавливаются требования к информированию собственников "
            "и нанимателей помещений о выполняемых работах, сроках "
            "устранения неисправностей и расходовании средств на содержание "
            "общего имущества. "
            "Предусматривается порядок предоставления сведений о выполненных "
            "работах и рассмотрения обращений жильцов."
        ),
    },
    {
        "number": "ZHKH-2026-003",
        "title": "ДЕМО: Порядок информирования об отключении коммунальных услуг",
        "description": (
            "Изменение порядка информирования потребителей о плановом "
            "прекращении предоставления коммунальных услуг. "
            "Плановое прекращение предоставления коммунальных услуг "
            "предполагает предварительное информирование потребителей. "
            "Определяются требования к срокам и способам уведомления "
            "потребителей об отключении холодного и горячего водоснабжения, "
            "электроснабжения и отопления. "
            "Также устанавливается порядок доведения до жильцов информации "
            "о причинах прекращения предоставления услуг и предполагаемых "
            "сроках их восстановления."
        ),
    },
]


USER_INTEREST_DESCRIPTION = (
    "Пользователь заинтересован в изменениях законодательства "
    "в сфере жилищно-коммунального хозяйства. "
    "Его интересуют порядок начисления и перерасчета платы "
    "за коммунальные услуги, требования к управляющим организациям, "
    "содержание многоквартирного дома, качество коммунальных услуг, "
    "а также порядок и сроки информирования жильцов "
    "об отключениях водоснабжения, отопления и электричества."
)


async def run(email: str) -> None:
    async with AsyncSessionLocal() as db:

        # 1. Находим пользователя.
        user = await db.scalar(
            select(User).where(
                User.email == email,
                User.is_active.is_(True),
            )
        )

        if user is None:
            raise RuntimeError(
                f"Активный пользователь {email} не найден."
            )

        chat = await db.scalar(
            select(ChatSession)
            .where(ChatSession.user_id == user.id)
            .order_by(ChatSession.id.desc())
            .limit(1)
        )

        if chat is None:
            raise RuntimeError(
                f"У пользователя {email} нет существующего чата."
            )

        print(f"Пользователь: {user.email}, ID: {user.id}")
        print(f"Чат для уведомлений: {chat.id}")

        interest = await db.scalar(
            select(UserLawInterest).where(
                UserLawInterest.user_id == user.id,
                UserLawInterest.topic_key.in_(
                    ["demo_zhkh", TOPIC_KEY]
                ),
            )
        )

        if interest is None:
            interest = UserLawInterest(
                user_id=user.id,
                chat_id=chat.id,
                topic_key=TOPIC_KEY,
                topic_label=TOPIC_LABEL,
                keywords=TOPIC_KEYWORDS,
                source_excerpt=USER_INTEREST_DESCRIPTION,
            )
            db.add(interest)
        else:
            interest.chat_id = chat.id
            interest.topic_key = TOPIC_KEY
            interest.topic_label = TOPIC_LABEL
            interest.keywords = TOPIC_KEYWORDS
            interest.source_excerpt = USER_INTEREST_DESCRIPTION

        now = datetime.now(timezone.utc)
        change_ids = []

        for item in LAW_CHANGES:

            document = await db.scalar(
                select(LawDocument).where(
                    LawDocument.number == item["number"]
                )
            )

            if document is None:
                document = LawDocument(
                    number=item["number"],
                    title=item["title"],
                    full_text=item["description"],
                    source_url=None,
                    published_at=now,
                    law_type="DEMO",
                    status="active",
                )
                db.add(document)
                await db.flush()
            else:
                document.title = item["title"]
                document.full_text = item["description"]

            change = await db.scalar(
                select(LawChange).where(
                    LawChange.document_id == document.id,
                    LawChange.change_title == item["title"],
                )
            )

            if change is None:
                change = LawChange(
                    document_id=document.id,
                    change_title=item["title"],
                    change_date=now,
                    diff={
                        "category": TOPIC_LABEL,
                        "tags": TOPIC_KEYWORDS,
                    },
                    description=item["description"],
                    source_url=None,
                )
                db.add(change)
                await db.flush()
            else:
                change.change_date = now
                change.created_at = now
                change.diff = {
                    "category": TOPIC_LABEL,
                    "tags": TOPIC_KEYWORDS,
                }
                change.description = item["description"]

            change_ids.append(change.id)

        await db.commit()

        print(f"Интерес пользователя: {TOPIC_LABEL}")
        print(f"ID тестовых изменений: {change_ids}")

        created_count = await dispatch_law_change_notifications(
            db,
            lookback_days=2,
            legacy_keyword_fallback=True,
            check_personal_relevance=True,
        )

        print(
            f"Создано новых уведомлений: {created_count}"
        )

        deliveries = (
            await db.execute(
                select(
                    LawChangeDelivery.notification_id,
                    LawChangeDelivery.payload_meta,
                ).where(
                    LawChangeDelivery.user_id == user.id,
                    LawChangeDelivery.change_id.in_(change_ids),
                )
            )
        ).all()

        print("\nСвязи уведомлений с чатами:")

        for delivery in deliveries:
            meta = delivery.payload_meta or {}

            print(
                f"Уведомление ID: {delivery.notification_id}; "
                f"chat_id: {meta.get('chat_id')}; "
                f"related_chat_ids: {meta.get('related_chat_ids')}"
            )

        if not deliveries:
            print(
                "Связи не созданы. Проверь результаты проверки "
                "релевантности и логи Backend."
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Создание тестовых уведомлений об изменениях в ЖКХ"
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
