from __future__ import annotations

import json
import logging
from typing import Sequence

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.law_changes import LawChange, LawDocument
from app.services.law_change_parser import (
    ParsedLawChange,
    is_consultant_index,
    is_consultant_source,
    parse_consultant_category,
    parse_consultant_index,
    parse_consultant_period_categories,
    parse_json_changes,
)

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "LegalAI-LawMonitor/1.0 (+https://ai-jurist.ru)",
    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
}


async def _fetch_text(client: httpx.AsyncClient, url: str) -> tuple[str, str | None]:
    response = await client.get(url)
    response.raise_for_status()
    content_type = response.headers.get("content-type")
    return response.text, content_type


async def collect_changes_from_source(
    client: httpx.AsyncClient,
    source_url: str,
) -> list[ParsedLawChange]:
    text, content_type = await _fetch_text(client, source_url)
    if "application/json" in (content_type or "") or text.lstrip().startswith("{"):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            return parse_json_changes(payload, source_url)

    if is_consultant_source(source_url):
        if is_consultant_index(source_url):
            period_url = parse_consultant_index(text, source_url)
            if not period_url:
                logger.warning("Consultant index did not expose a latest period link: %s", source_url)
                return []
            period_text, _ = await _fetch_text(client, period_url)
            categories = parse_consultant_period_categories(period_text, period_url)
            if not categories:
                logger.warning("Consultant period page has no categories: %s", period_url)
                return []
            collected: list[ParsedLawChange] = []
            for category_name, category_url in categories[: settings.LAW_CHANGE_MAX_CATEGORIES]:
                try:
                    category_text, _ = await _fetch_text(client, category_url)
                except Exception:
                    logger.exception("Failed to fetch consultant category: %s", category_url)
                    continue
                collected.extend(
                    parse_consultant_category(category_text, category_url, category=category_name)
                )
            return collected

        categories = parse_consultant_period_categories(text, source_url)
        if categories:
            collected: list[ParsedLawChange] = []
            for category_name, category_url in categories[: settings.LAW_CHANGE_MAX_CATEGORIES]:
                try:
                    category_text, _ = await _fetch_text(client, category_url)
                except Exception:
                    logger.exception("Failed to fetch consultant category: %s", category_url)
                    continue
                collected.extend(
                    parse_consultant_category(category_text, category_url, category=category_name)
                )
            return collected

        return parse_consultant_category(text, source_url)

    return []


async def _get_or_create_document(db: AsyncSession, change: ParsedLawChange) -> LawDocument:
    document_number = (change.document_number or change.title[:50]).strip()
    result = await db.execute(select(LawDocument).where(LawDocument.number == document_number))
    document = result.scalar_one_or_none()
    if document is not None:
        return document

    document = LawDocument(
        title=(change.document_title or change.title)[:500],
        number=document_number[:50],
        source_url=change.source_url[:1000],
        law_type=change.category,
        status="active",
    )
    db.add(document)
    await db.flush()
    return document


async def persist_parsed_changes(
    db: AsyncSession,
    parsed_changes: Sequence[ParsedLawChange],
) -> list[LawChange]:
    created: list[LawChange] = []
    for change in parsed_changes:
        title = change.title.strip()
        if not title:
            continue
        existing = await db.execute(
            select(LawChange).where(
                LawChange.change_title == title,
                LawChange.source_url == change.source_url,
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue

        document = await _get_or_create_document(db, change)
        law_change = LawChange(
            document_id=document.id,
            change_title=title[:500],
            change_date=change.change_date,
            description=change.description,
            source_url=change.source_url[:1000],
            new_version=change.description,
            diff={"category": change.category} if change.category else None,
        )
        db.add(law_change)
        created.append(law_change)

    if created:
        await db.commit()
        for item in created:
            await db.refresh(item)
    return created


async def monitor_sources(source_urls: Sequence[str] | None = None) -> list[LawChange]:
    urls = list(source_urls or settings.law_change_source_list())
    if not urls:
        logger.warning("Law monitoring skipped: no sources configured")
        return []

    timeout = httpx.Timeout(settings.LAW_CHANGE_HTTP_TIMEOUT, connect=10.0)
    created: list[LawChange] = []
    async with httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=timeout, follow_redirects=True) as client:
        async with AsyncSessionLocal() as db:
            for source_url in urls:
                try:
                    parsed = await collect_changes_from_source(client, source_url)
                except Exception:
                    logger.exception("Law source failed: %s", source_url)
                    continue
                if not parsed:
                    logger.info("Law source returned no changes: %s", source_url)
                    continue
                created.extend(await persist_parsed_changes(db, parsed))
    return created
