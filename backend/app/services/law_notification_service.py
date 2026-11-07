from __future__ import annotations

import logging
import hashlib
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.chat import ChatSession
from app.models.chat_law_reference import LawChangeNorm
from app.models.law_reference_assessment import (
    LawReferenceAssessment,
    LawChangeDelivery,
)
from app.models.law_changes import LawChange
from app.models.notification import Notification
from app.models.user import User
from app.models.user_law_interest import UserLawInterest

from app.services.law_topic_service import (
    build_change_search_text,
    change_matches_interest,
    interest_match_score,
)

from app.services.law_relevance_service import (
    assess_law_change_relevance,
    assess_law_reference_relevance,
    LawRelevanceResult,
    GENERIC_ERROR,
    LAW_ANALYSIS_PROMPT,
    USER_MATCH_PROMPT,
)

from app.services.law_analysis_schema import (
    LAW_ANALYSIS_FUNCTION,
    build_user_match_function,
)

from app.services.law_reference_service import (
    find_references_for_change,
)

from app.services.law_user_context import (
    load_law_user_context,
    load_reference_user_context,
)

from app.services.notification_bus import publish_notification
from app.services.answer_norms import document_label


logger = logging.getLogger(__name__)


def _format_law_change_message(
    change: LawChange,
    topic_label: str,
) -> str:

    change_title = (
        (change.change_title or "").strip()
        or "Изменение законодательства"
    )

    date_str = None

    if change.change_date is not None:
        try:
            date_str = change.change_date.date().isoformat()
        except Exception:
            date_str = None

    description = (
        (change.description or "").strip()
        or "Описание изменения не предоставлено источником."
    )

    link = (change.source_url or "").strip()
    lines = [
        f"По теме «{topic_label}» обнаружено изменение законодательства.",
        f"📄 {change_title}",
        f"📅 Дата: {date_str}" if date_str else None,
        f"🔗 Источник: {link}" if link else None,
        "",
        "Что изменилось:",
        description,
    ]
    return "\n".join(line for line in lines if line is not None).strip()



def _norm_label(reference) -> str:

    pieces = [
        document_label(reference.document_key),
        (
            f"статья {reference.article}"
            if reference.article
            else "правовой документ"
        ),
    ]

    if reference.part:
        pieces.append(f"часть {reference.part}")

    if reference.point:
        pieces.append(f"пункт {reference.point}")

    return ", ".join(pieces)


def _format_article_change_message(
    change: LawChange,
    references,
    *,
    document_change=False,
) -> str:

    labels = list(
        dict.fromkeys(
            _norm_label(r)
            for r in references
        )
    )

    sources = list(
        dict.fromkeys(
            r.source_url
            for r in references
            if r.source_url
        )
    )

    lines = [
        (
            "Изменился закон, использованный в ответе на ваш прежний вопрос. "
            "Изменение конкретной статьи пока не подтверждено."
            if document_change
            else
            "Изменена норма, использованная в ответе на ваш прежний вопрос."
        ),
        "Возможно, стоит пересмотреть прежний ответ. Откройте связанный чат.",
        "Нормы из прежнего ответа: " + "; ".join(labels),
        "",
        "Что изменилось:",
        (
            (change.description or "").strip()
            or "Описание изменения не предоставлено источником."
        ),
    ]

    if change.change_date is not None:
        lines.append(
            f"Дата изменения: {change.change_date.date().isoformat()}"
        )

    if change.source_url:
        lines.append(
            f"Источник изменения: {change.source_url}"
        )

    lines.extend(
        f"Норма из прежнего ответа: {source}"
        for source in sources
    )

    return "\n".join(lines)


def _fingerprint(change, reference, context):

    payload = {
        "change": [
            change.change_title,
            change.description,
            change.old_version,
            change.new_version,
            (
                change.change_date.isoformat()
                if change.change_date
                else None
            ),
        ],
        "norm": [
            reference.document_key,
            reference.article,
            reference.part,
            reference.point,
            reference.source_revision,
            reference.source_sha256,
            reference.source_text,
            reference.situation_excerpt,
        ],
        "context": context,
        "model": settings.GIGACHAT_MODEL,
        "prompts": [
            LAW_ANALYSIS_PROMPT,
            USER_MATCH_PROMPT,
        ],
        "schemas": [
            LAW_ANALYSIS_FUNCTION,
            build_user_match_function([]),
        ],
    }

    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
        ).encode()
    ).hexdigest()


async def _store_assessment(
    db,
    *,
    change_id,
    reference_id,
    result,
    fingerprint,
):

    values = dict(
        change_id=change_id,
        reference_id=reference_id,
        status=result.status or "error",
        reason=result.reason,
        conditions=list(result.conditions),
        law_analysis=result.law_analysis,
        failure_stage=result.failure_stage,
        error_code=result.error_code,
        model=settings.GIGACHAT_MODEL,
        input_fingerprint=fingerprint,
        checked_at=datetime.now(timezone.utc),
    )

    if db.bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert

    statement = insert(
        LawReferenceAssessment
    ).values(**values)

    updates = {
        key: getattr(statement.excluded, key)
        for key in values
        if key not in {"change_id", "reference_id"}
    }

    await db.execute(
        statement.on_conflict_do_update(
            index_elements=[
                "change_id",
                "reference_id",
            ],
            set_=updates,
        )
    )


async def dispatch_law_change_notifications(
    db: AsyncSession,
    *,
    lookback_days: int = 2,
    legacy_keyword_fallback: bool = False,
    check_personal_relevance: bool = False,
) -> int:

    """Notify when an explicitly changed norm was cited in the user's chat.

    Personal impact analysis is optional; article-change notices make no claim of it.
    Legacy keyword interests still require explicit opt-in.
    """

    since = (
        datetime.now(timezone.utc)
        - timedelta(days=lookback_days)
    )

    pending = select(
        LawReferenceAssessment.change_id
    ).where(
        LawReferenceAssessment.status.in_(
            ["insufficient_data", "error"]
        )
    )

    changes = list(
        await db.scalars(
            select(LawChange)
            .where(
                or_(
                    LawChange.created_at >= since,
                    LawChange.id.in_(pending),
                    LawChange.diff[
                        "norm_mapping_pending"
                    ].as_boolean() == True,
                )
            )
            .order_by(LawChange.created_at.asc())
        )
    )

    if not changes:
        return 0

    active_users = {
        u.id: u
        for u in await db.scalars(
            select(User).where(
                User.is_active == True
            )
        )
    }

    scoped_changes = set(
        await db.scalars(
            select(LawChangeNorm.change_id)
            .where(
                LawChangeNorm.change_id.in_(
                    [c.id for c in changes]
                )
            )
            .distinct()
        )
    )

    interests = (
        list(
            await db.scalars(
                select(UserLawInterest)
            )
        )
        if legacy_keyword_fallback
        else []
    )

    created_count = 0
    dirty = False
    pending_events = []

    legacy_contexts = {}
    reference_contexts = {}
    analyses = {}
    analysis_errors = {}

    for change in changes:

        evidence = (
            change.diff or {}
        ).get("norm_evidence", [])

        if (
            (change.diff or {})
            .get("scope_resolution", {})
            .get("status") == "unresolved"
            or (
                evidence
                and all(
                    item.get("method")
                    == "overview_document_identity"
                    for item in evidence
                )
            )
        ):
            logger.info(
                "Notification held: article scope unconfirmed, change_id=%s",
                change.id,
            )
            continue

        candidates = {}

        if change.id in scoped_changes:

            references = await find_references_for_change(
                db,
                change_id=change.id,
            )

            owners = (
                dict(
                    (
                        await db.execute(
                            select(
                                ChatSession.id,
                                ChatSession.user_id,
                            ).where(
                                ChatSession.id.in_(
                                    [r.chat_id for r in references]
                                )
                            )
                        )
                    ).all()
                )
                if references
                else {}
            )

            for reference in references:
                user_id = owners.get(reference.chat_id)

                if user_id in active_users:
                    candidates.setdefault(
                        user_id,
                        [],
                    ).append(
                        (reference, None)
                    )

        elif legacy_keyword_fallback:

            category = (
                change.diff.get("category")
                if isinstance(change.diff, dict)
                else None
            )

            text = build_change_search_text(
                title=change.change_title,
                description=change.description,
                category=category,
            )

            for interest in interests:

                if (
                    interest.user_id in active_users
                    and change_matches_interest(
                        text,
                        interest.keywords or [],
                    )
                ):
                    candidates.setdefault(
                        interest.user_id,
                        [],
                    ).append(
                        (None, interest)
                    )

            # Сначала проверяем наиболее подходящий интерес.
            # Это важно, когда одно изменение совпало
            # сразу с несколькими темами пользователя.
            for user_id, situations in candidates.items():

                situations.sort(
                    key=lambda item: (
                        interest_match_score(
                            text,
                            item[1].keywords or [],
                        )
                        if item[1] is not None
                        else -1
                    ),
                    reverse=True,
                )

        else:
            logger.info(
                "Law change lacks explicit affected norms: change_id=%s",
                change.id,
            )

        title = (
            f"LAW_CHANGE#{change.id}: "
            f"{(change.change_title or '').strip() or 'Изменение законодательства'}"
        )[:255]

        for user_id, situations in candidates.items():

            delivered = await db.scalar(
                select(LawChangeDelivery.id).where(
                    LawChangeDelivery.user_id == user_id,
                    LawChangeDelivery.change_id == change.id,
                )
            )

            existing = await db.scalar(
                select(Notification.id).where(
                    Notification.user_id == user_id,
                    Notification.notification_type == "law_change",
                    Notification.title == title,
                )
            )

            if delivered is not None or existing is not None:
                continue

            confirmed = []

            for reference, interest in situations:

                if reference is not None:

                    if not check_personal_relevance:
                        confirmed.append(
                            (reference, None, None)
                        )
                        continue

                    if reference.id not in reference_contexts:
                        reference_contexts[reference.id] = (
                            await load_reference_user_context(
                                db,
                                user_id=user_id,
                                reference=reference,
                            )
                        )

                    context = reference_contexts[reference.id]

                    fingerprint = _fingerprint(
                        change,
                        reference,
                        context,
                    )

                    saved = await db.scalar(
                        select(LawReferenceAssessment)
                        .where(
                            LawReferenceAssessment.change_id == change.id,
                            LawReferenceAssessment.reference_id == reference.id,
                        )
                        .execution_options(
                            populate_existing=True
                        )
                    )

                    if (
                        saved is not None
                        and saved.input_fingerprint == fingerprint
                        and saved.status in {
                            "irrelevant",
                            "insufficient_data",
                        }
                    ):
                        result = LawRelevanceResult(
                            False,
                            saved.reason,
                            saved.status,
                            tuple(saved.conditions),
                            saved.law_analysis,
                            saved.failure_stage,
                            saved.error_code,
                        )

                    else:

                        try:

                            if not context.strip():
                                result = LawRelevanceResult(
                                    False,
                                    "Нет заявлений пользователя для проверки.",
                                    "insufficient_data",
                                )

                            elif change.id in analysis_errors:
                                result = analysis_errors[change.id]

                            else:
                                result = (
                                    await assess_law_reference_relevance(
                                        change,
                                        reference,
                                        user_context=context,
                                        law_analysis=analyses.get(change.id),
                                    )
                                )

                            if (
                                result.status not in {
                                    "relevant",
                                    "irrelevant",
                                    "insufficient_data",
                                    "error",
                                }
                                or result.relevant
                                is not (result.status == "relevant")
                            ):
                                result = LawRelevanceResult(
                                    False,
                                    GENERIC_ERROR,
                                    "error",
                                    failure_stage="result_validation",
                                    error_code="Inconsistent relevance result",
                                )

                        except Exception as exc:

                            result = LawRelevanceResult(
                                False,
                                GENERIC_ERROR,
                                "error",
                                failure_stage="reference_check",
                                error_code=type(exc).__name__,
                            )

                        await _store_assessment(
                            db,
                            change_id=change.id,
                            reference_id=reference.id,
                            result=result,
                            fingerprint=fingerprint,
                        )

                        dirty = True

                    if result.law_analysis is not None:
                        analyses[change.id] = result.law_analysis

                    if (
                        result.status == "error"
                        and result.failure_stage
                        in {"connection", "law_analysis"}
                    ):
                        analysis_errors[change.id] = result

                    accepted = (
                        result.status == "relevant"
                        and result.relevant is True
                    )

                else:

                    context_key = (
                        user_id,
                        interest.chat_id,
                    )

                    if context_key not in legacy_contexts:
                        legacy_contexts[context_key] = (
                            await load_law_user_context(
                                db,
                                user_id=user_id,
                                chat_id=interest.chat_id,
                            )
                        )

                    result = await assess_law_change_relevance(
                        change,
                        interest,
                        user_context=legacy_contexts[context_key],
                    )

                    accepted = (
                        result.relevant is True
                        and result.status in {None, "relevant"}
                    )

                if accepted:
                    confirmed.append(
                        (reference, interest, result)
                    )

                else:
                    logger.info(
                        "Law relevance not confirmed: change_id=%s user_id=%s status=%s",
                        change.id,
                        user_id,
                        result.status,
                    )

            if not confirmed:
                continue

            reference, interest, result = confirmed[0]

            chat_ids = sorted(
                {
                    r.chat_id if r is not None else i.chat_id
                    for r, i, _ in confirmed
                }
                - {None}
            )

            reference_ids = [
                r.id
                for r, _, _ in confirmed
                if r is not None
            ]

            norms = [
                dict(
                    document_key=r.document_key,
                    article=r.article,
                    part=r.part,
                    point=r.point,
                )
                for r, _, _ in confirmed
                if r is not None
            ]

            label = (
                _norm_label(reference)
                if reference is not None
                else interest.topic_label
            )

            article_notice = (
                reference is not None
                and not check_personal_relevance
            )

            if article_notice:

                changed_norms = (
                    await db.scalars(
                        select(LawChangeNorm).where(
                            LawChangeNorm.change_id == change.id
                        )
                    )
                ).all()

                document_change = any(
                    not n.article
                    for n in changed_norms
                )

                message = _format_article_change_message(
                    change,
                    [
                        r
                        for r, _, _ in confirmed
                    ],
                    document_change=document_change,
                )

                reasons = [
                    (
                        "Изменённый закон использовался в прежнем ответе; "
                        "конкретная статья не подтверждена."
                        if document_change
                        else
                        "Изменённая норма использовалась в ответе на ваш прежний вопрос."
                    )
                ]

            else:

                message = _format_law_change_message(
                    change,
                    label,
                )

                reasons = list(
                    dict.fromkeys(
                        res.reason
                        for _, _, res in confirmed
                    )
                )

                message += (
                    "\n\nПочему это касается вашей ситуации:\n"
                    + "\n".join(reasons)
                )

                if reference is not None:
                    message += (
                        f"\nНорма из прежнего ответа: "
                        f"{reference.source_url}"
                    )

            meta = {
                "law_change_id": change.id,
                "chat_id": (
                    chat_ids[0]
                    if chat_ids
                    else None
                ),
                "related_chat_ids": chat_ids,
                "reference_ids": reference_ids,
                "norms": list(
                    {
                        tuple(norm.values()): norm
                        for norm in norms
                    }.values()
                ),
                "reasons": reasons,
                "notification_basis": (
                    "article_change"
                    if article_notice
                    else "personal_relevance"
                ),
                "personal_relevance_checked": not article_notice,
            }

            if interest is not None:
                meta.update(
                    topic_key=interest.topic_key,
                    topic_label=interest.topic_label,
                )

            try:

                async with db.begin_nested():

                    notification = Notification(
                        user_id=user_id,
                        title=title,
                        message=message,
                        notification_type="law_change",
                        severity="medium",
                        is_read=False,
                    )

                    db.add(notification)

                    await db.flush()

                    db.add(
                        LawChangeDelivery(
                            user_id=user_id,
                            change_id=change.id,
                            notification_id=notification.id,
                            payload_meta=meta,
                        )
                    )

                    await db.flush()

                    if reference_ids and not article_notice:
                        await db.execute(
                            update(LawReferenceAssessment)
                            .where(
                                LawReferenceAssessment.change_id == change.id,
                                LawReferenceAssessment.reference_id.in_(
                                    reference_ids
                                ),
                            )
                            .values(
                                notification_id=notification.id
                            )
                        )

            except IntegrityError:

                duplicate = await db.scalar(
                    select(LawChangeDelivery.id).where(
                        LawChangeDelivery.user_id == user_id,
                        LawChangeDelivery.change_id == change.id,
                    )
                )

                if duplicate is None:
                    raise

                continue

            dirty = True
            created_count += 1

            pending_events.append(
                (
                    user_id,
                    {
                        "title": title,
                        "message": message,
                        "type": "law_change",
                        "severity": "medium",
                        "id": notification.id,
                        "meta": meta,
                    },
                )
            )

        if (
            not check_personal_relevance
            and isinstance(change.diff, dict)
            and change.diff.get("norm_mapping_pending")
        ):
            change.diff = {
                **change.diff,
                "norm_mapping_pending": False,
            }

            dirty = True

    if dirty:
        await db.commit()

    # Pub/sub must not announce a notification
    # before its database commit succeeds.
    for user_id, payload in pending_events:

        try:
            publish_notification(
                payload,
                user_id=user_id,
            )

        except Exception:
            logger.warning(
                "Redis publish failed for committed law notification user_id=%s",
                user_id,
            )

    return created_count
