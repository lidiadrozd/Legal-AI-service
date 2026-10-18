from __future__ import annotations

import json
import asyncio
import logging
from typing import Sequence
from urllib.parse import urlparse
from pathlib import Path
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.law_changes import LawChange, LawDocument
from app.models.law_monitor_state import LawMonitorState
from app.services.law_reference_service import save_change_norms
from app.models.chat_law_reference import LawChangeNorm, ChatLawReference
from app.services.answer_norms import CODE_URLS
from app.services.legal_sources import NormIdentity
from app.services.curated_law_changes import load_curated_changes, CuratedSourceError
from app.services.legal_sources import load_legal_source_catalog
from app.services.consultant_norm_changes import (consultant_document_id, catalog_document_keys,
    extract_linked_amendments, amendment_target_urls)
from app.services.law_change_parser import (
    ParsedLawChange,
    is_consultant_index,
    is_consultant_source,
    parse_consultant_category,
    parse_consultant_index,
    parse_consultant_periods,
    consultant_period_dates,
    parse_consultant_period_categories,
    parse_json_changes,
)

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "LegalAI-LawMonitor/1.0 (+https://ai-jurist.ru)",
    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
}


async def _get_source_response(client: httpx.AsyncClient, url: str) -> httpx.Response:
    """Retry one timed-out read of a public GET; never retry HTTP refusals."""
    for attempt in range(2):
        try:
            # httpx timeouts apply to individual network operations; bound
            # the entire GET too, including redirects and transport retries.
            return await asyncio.wait_for(client.get(url),
                timeout=max(1, settings.LAW_CHANGE_HTTP_TIMEOUT * 2))
        except httpx.ReadTimeout:
            if attempt:
                raise


async def _fetch_text(client: httpx.AsyncClient, url: str) -> tuple[str, str | None]:
    response = await _get_source_response(client, url)
    response.raise_for_status()
    content_type = response.headers.get("content-type")
    return response.text, content_type


async def enrich_consultant_changes(client, changes, document_keys=None):
    # Optional RAG metadata and previously used sources help resolve article links.
    # The original dated/numbered heading itself identifies a whole-law change.
    candidates = {}
    catalog = catalog_document_keys(load_legal_source_catalog(Path(settings.RAG_DOCS_PATH)))
    for doc_id, key in list(catalog.items()) + [(consultant_document_id(url), key) for key, url in CODE_URLS.items()] + list((document_keys or {}).items()):
        if doc_id:
            candidates.setdefault(doc_id, set()).add(key)
    keys = {doc_id: next(iter(values)) for doc_id, values in candidates.items() if len(values) == 1}
    cache = {}
    remaining = max(0, settings.LAW_CHANGE_MAX_AMENDMENT_PAGES)
    failed_fetches = 0

    async def fetch(url):
        nonlocal remaining, failed_fetches
        if url not in cache:
            if not remaining or not consultant_document_id(url):
                failed_fetches += 1
                return None
            remaining -= 1
            try:
                response = await _get_source_response(client, url)
                response.raise_for_status()
                if not consultant_document_id(str(response.url)) or len(response.content) > 2 * 1024 * 1024:
                    cache[url] = None
                else:
                    cache[url] = (response.text, str(response.url))
            except Exception as exc:
                logger.warning("Amendment page unavailable: error_type=%s", type(exc).__name__)
                cache[url] = None
        if cache.get(url) is None:
            failed_fetches += 1
        return cache.get(url)

    result = []
    for change in changes:
        failures_before = failed_fetches
        if change.affected_norms:
            result.append(change)
            continue
        fallback = None
        if change.document_key and change.change_date is not None:
            fallback = replace(change, affected_norms=(NormIdentity(change.document_key),),
                scope_resolution={"status": "unresolved", "reason": "amendment_unresolved" if change.amendment_source_urls else "amendment_link_missing"},
                norm_evidence=({"method": "overview_document_identity", "document_key": change.document_key,
                                "publication_url": change.source_url, "scope": "document"},))
        if not change.amendment_source_urls:
            result.append(replace(fallback or change, norm_resolution_pending=bool(change.amendment_source_urls)))
            continue
        base_id = consultant_document_id(change.source_url)
        if base_id not in keys:
            base = await fetch(change.source_url)
            canonical_id = consultant_document_id(base[1]) if base else None
            if canonical_id in keys:
                keys[base_id] = keys[canonical_id]
            elif canonical_id and change.document_key:
                keys[canonical_id] = keys[base_id] = change.document_key
            else:
                result.append(replace(fallback or change, norm_resolution_pending=bool(change.amendment_source_urls)))
                continue
        base_key = keys[base_id]
        confirmed = []
        for publication_url in change.amendment_source_urls:
            page = await fetch(publication_url)
            if not page:
                continue
            html, final_url = page
            # A provider redirect can identify a historical edition as the same
            # catalog document. Never resolve identities from similar law names.
            for target_url in amendment_target_urls(html, final_url):
                target_id = consultant_document_id(target_url)
                if target_id not in keys:
                    target = await fetch(target_url)
                    canonical_id = consultant_document_id(target[1]) if target else None
                    if canonical_id in keys:
                        keys[target_id] = keys[canonical_id]
            confirmed.extend(item for item in extract_linked_amendments(html, final_url, keys)
                             if item.norm.document_key == base_key)
        if confirmed:
            norms = tuple(dict.fromkeys(item.norm for item in confirmed))
            evidence = tuple(item.evidence for item in confirmed)
            instructions = list(dict.fromkeys(item.evidence["instruction"] for item in confirmed))
            result.append(replace(change, affected_norms=norms, norm_evidence=evidence,
                scope_resolution={"status": "confirmed", "method": "explicit_instruction", "partial": failed_fetches > failures_before},
                norm_resolution_pending=failed_fetches > failures_before,
                description=change.description + "\n\nПодтверждённые поправки:\n" + "\n".join(instructions)))
        else:
            result.append(replace(fallback or change, norm_resolution_pending=bool(change.amendment_source_urls)))
    return result


class SourceFormatError(RuntimeError):
    """A downloaded page cannot be treated as a successful source check."""


async def collect_changes_from_source(client: httpx.AsyncClient, source_url: str,
                                      document_keys=None, *, checkpoint=None, progress=None):
    checkpoint = checkpoint or {}
    progress = progress if progress is not None else {}
    progress["source_success"] = False
    text, content_type = await _fetch_text(client, source_url)
    if "application/json" in (content_type or "") or text.lstrip().startswith("{"):
        payload = json.loads(text)
        if not isinstance(payload, dict) or not isinstance(payload.get("changes"), list):
            raise SourceFormatError("Missing change list")
        progress["source_success"] = True
        return parse_json_changes(payload, source_url)
    if not is_consultant_source(source_url):
        raise SourceFormatError("Unsupported source format")

    async def collect_page(page_text, page_url):
        categories = parse_consultant_period_categories(page_text, page_url)
        if not categories:
            changes = parse_consultant_category(page_text, page_url)
            if not changes:
                raise SourceFormatError("No recognizable category entries")
            return changes, True
        # This monitor understands laws and codes, rather than every agency's act.
        categories = [(name, url) for name, url in categories
                      if "кодекс" in name.casefold() or ("федеральн" in name.casefold() and "закон" in name.casefold())]
        collected = []
        complete = len(categories) <= settings.LAW_CHANGE_MAX_CATEGORIES
        for name, url in categories[:settings.LAW_CHANGE_MAX_CATEGORIES]:
            try:
                category_text, _ = await _fetch_text(client, url)
                entries = parse_consultant_category(category_text, url, category=name)
                if not entries:
                    raise SourceFormatError("No recognizable category entries")
                collected.extend(entries)
            except Exception as exc:
                complete = False
                logger.warning("Category check incomplete: error_type=%s", type(exc).__name__)
        return collected, complete

    if is_consultant_index(source_url) or urlparse(source_url).path.rstrip("/") == "/document/cons_doc_LAW_33770":
        periods = parse_consultant_periods(text, source_url)
        if not periods:
            raise SourceFormatError("No recognizable periods")
        completed = set(checkpoint.get("completed_periods", []))
        pending = dict(checkpoint.get("pending_periods", {}))
        latest = periods[0][1]
        for label, url in reversed(periods):
            if url not in completed or url == latest:
                pending[url] = label
        ranges = [dates for label, _ in periods if (dates := consultant_period_dates(label))]
        progress["available_periods"] = [{"label":label, "url":url} for label, url in periods]
        if ranges:
            progress["earliest_available_start"] = min(d[0] for d in ranges).date().isoformat()
            progress["latest_available_end"] = max(d[1] for d in ranges).date().isoformat()
        collected = []
        available_urls = {url for _, url in periods}
        queue = [url for _, url in reversed(periods) if url in pending]
        queue += [url for url in pending if url not in available_urls]
        for url in queue[:max(0, settings.LAW_CHANGE_MAX_PERIODS_PER_RUN)]:
            label = pending[url]
            try:
                page_text, _ = await _fetch_text(client, url)
                entries, complete = await collect_page(page_text, url)
                collected.extend(entries)
                if complete:
                    completed.add(url)
                    del pending[url]
            except Exception as exc:
                logger.warning("Period check incomplete: error_type=%s", type(exc).__name__)
        complete_ranges = [consultant_period_dates(label) for label, url in periods
                           if url in completed and url not in pending and consultant_period_dates(label)]
        if complete_ranges:
            covered = max(d[1] for d in complete_ranges).date().isoformat()
            progress["coverage_through"] = max(covered, checkpoint.get("coverage_through", covered))
        progress.update(completed_periods=sorted(completed), pending_periods=pending,
                        source_success=not pending)
        return await enrich_consultant_changes(client, collected, document_keys)
    collected, complete = await collect_page(text, source_url)
    progress["source_success"] = complete
    return await enrich_consultant_changes(client, collected, document_keys)


def _resolution_info(change, *, attempts=1):
    now = datetime.now(timezone.utc)
    return {"state": "pending" if change.norm_resolution_pending else "resolved",
            "amendment_source_urls": list(change.amendment_source_urls),
            "document_key": change.document_key, "document_number": change.document_number,
            "document_title": change.document_title, "category": change.category,
            "overview_description": change.description.split("\n\nПодтверждённые поправки:", 1)[0],
            "last_attempt_at": now.isoformat(), "next_attempt_at": (now + timedelta(days=1)).isoformat(),
            "attempts": attempts}


async def retry_pending_norms(db, client, document_keys):
    """Retry saved publication URLs even after their overview leaves the index."""
    now = datetime.now(timezone.utc)
    pending = list(await db.scalars(select(LawChange).where(
        LawChange.diff["norm_resolution"]["state"].as_string() == "pending").order_by(LawChange.id)))
    due = []
    for row in pending:
        info = row.diff["norm_resolution"]
        try:
            next_attempt = datetime.fromisoformat(info["next_attempt_at"])
            if next_attempt.tzinfo is None:
                next_attempt = next_attempt.replace(tzinfo=timezone.utc)
        except (KeyError, TypeError, ValueError):
            next_attempt = now
        if next_attempt <= now:
            due.append(row)
    due.sort(key=lambda row: row.diff["norm_resolution"].get("last_attempt_at", ""))
    for row in due[:max(0, settings.LAW_CHANGE_MAX_PENDING_CHANGES)]:
        info = row.diff["norm_resolution"]
        change = ParsedLawChange(title=row.change_title, change_date=row.change_date,
            description=info.get("overview_description") or row.description or "",
            source_url=row.source_url, document_number=info.get("document_number"),
            document_title=info.get("document_title"), category=info.get("category"),
            amendment_source_urls=tuple(info.get("amendment_source_urls", [])),
            document_key=info.get("document_key"))
        enriched, = await enrich_consultant_changes(client, [change], document_keys)
        await persist_parsed_changes(db, [enriched])
    return len(due[:max(0, settings.LAW_CHANGE_MAX_PENDING_CHANGES)])


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
    enriched = False
    for change in parsed_changes:
        title = change.title.strip()
        if not title:
            continue
        existing = await db.execute(
            select(LawChange).where(
                LawChange.change_title == title,
                LawChange.source_url == change.source_url,
                LawChange.change_date == change.change_date,
            )
        )
        existing_change = existing.scalar_one_or_none()
        if existing_change is not None:
            mapped = set()
            if change.norm_evidence or change.scope_resolution:
                mapped = set((await db.execute(select(LawChangeNorm.document_key, LawChangeNorm.article,
                    LawChangeNorm.part, LawChangeNorm.point).where(LawChangeNorm.change_id == existing_change.id))).all())
            old_diff = dict(existing_change.diff) if isinstance(existing_change.diff, dict) else {}
            if change.scope_resolution and not (
                (old_diff.get("scope_resolution", {}).get("status") == "confirmed" or any(row[1] for row in mapped))
                and change.scope_resolution.get("status") != "confirmed"):
                old_diff["scope_resolution"] = change.scope_resolution
                existing_change.diff = old_diff
                enriched = True
            old_resolution = old_diff.get("norm_resolution", {})
            if change.amendment_source_urls and (old_resolution.get("state") != "resolved" or not change.norm_resolution_pending):
                old_diff["norm_resolution"] = _resolution_info(change, attempts=old_resolution.get("attempts", 0) + 1)
                existing_change.diff = old_diff
                enriched = True
            if change.norm_evidence:
                # A temporary source failure must not broaden an already precise mapping.
                added = [norm for norm in change.affected_norms
                         if (norm.document_key, norm.article, norm.part, norm.point) not in mapped
                         and (norm.article or not any(row[0] == norm.document_key and row[1] for row in mapped))]
                old_diff = existing_change.diff if isinstance(existing_change.diff, dict) else {}
                fallback_keys = {e.get("document_key") for e in old_diff.get("norm_evidence", [])
                                 if e.get("method") == "overview_document_identity"}
                precise_keys = {n.document_key for n in change.affected_norms if n.article} if not change.norm_resolution_pending else set()
                remove_keys = fallback_keys & precise_keys
                if remove_keys:
                    from sqlalchemy import delete
                    await db.execute(delete(LawChangeNorm).where(LawChangeNorm.change_id == existing_change.id,
                        LawChangeNorm.document_key.in_(remove_keys), LawChangeNorm.article == ""))
                    enriched = True
                if added:
                    await save_change_norms(db, change_id=existing_change.id, norms=added)
                    diff = dict(existing_change.diff) if isinstance(existing_change.diff, dict) else {}
                    diff.update(norm_evidence=list(change.norm_evidence), norm_mapping_pending=True)
                    existing_change.diff = diff
                    existing_change.description = change.description
                    enriched = True
            continue

        document = await _get_or_create_document(db, change)
        law_change = LawChange(
            document_id=document.id,
            change_title=title[:500],
            change_date=change.change_date,
            description=change.description,
            source_url=change.source_url[:1000],
            old_version=change.old_version,
            new_version=change.new_version,
            diff=({**({"category": change.category} if change.category else {}),
                   **({"norm_evidence": list(change.norm_evidence)} if change.norm_evidence else {}),
                   **({"norm_resolution": _resolution_info(change)} if change.amendment_source_urls else {}),
                   **({"scope_resolution": change.scope_resolution} if change.scope_resolution else {}),
                   "norm_mapping_pending": True}),
        )
        db.add(law_change)
        if change.affected_norms:
            await db.flush()
            await save_change_norms(db, change_id=law_change.id, norms=list(change.affected_norms))
        created.append(law_change)

    if created or enriched:
        await db.commit()
        for item in created:
            await db.refresh(item)
    return created


async def refresh_tracked_article_snapshots(db, client, known_sources):
    """Capture only laws actually used in chats; no manually maintained catalog."""
    from app.services.article_change_detection import (
        build_article_snapshot, compare_article_snapshots, snapshot_change)
    by_key = {}
    for url, key in known_sources:
        if consultant_document_id(url):
            by_key.setdefault(key, url)
    created = []
    # Oldest attempted snapshots first prevents starvation when there are many laws.
    states = list(await db.scalars(select(LawMonitorState).where(
        LawMonitorState.source_url.like("article_snapshot:%"))))
    attempts = {s.source_url.removeprefix("article_snapshot:"): s.last_attempt_at for s in states}
    ordered = sorted(by_key, key=lambda k: str(attempts.get(k) or ""))
    for key in ordered[:max(0, settings.LAW_CHANGE_MAX_SNAPSHOT_DOCUMENTS)]:
        state_key = "article_snapshot:" + key
        state = await db.scalar(select(LawMonitorState).where(LawMonitorState.source_url == state_key))
        if state is None:
            state = LawMonitorState(source_url=state_key, progress={}, coverage_gap=False)
            db.add(state)
        state.last_attempt_at = datetime.now(timezone.utc)
        try:
            url = CODE_URLS.get(key) or by_key[key]
            # Always read the provider's root/current page, not a historical fragment.
            url = "https://www.consultant.ru/document/cons_doc_LAW_" + consultant_document_id(url) + "/"
            response = await _get_source_response(client, url)
            response.raise_for_status()
            if len(response.content) > 2 * 1024 * 1024:
                raise ValueError("document_too_large")
            snapshot = build_article_snapshot(response.text, str(response.url), key)
            status, evidence = compare_article_snapshots((state.progress or {}).get("snapshot"), snapshot)
            # Preserve the previous baseline when identity/structure/order is uncertain.
            if status not in {"older_edition_ignored", "incomplete_or_removed_articles"}:
                if evidence:
                    created.extend(await persist_parsed_changes(db, [snapshot_change(snapshot, evidence)]))
                state.progress = {"kind": "article_snapshot", "status": status, "snapshot": snapshot}
                state.last_success_at = datetime.now(timezone.utc)
                state.last_error = None
            else:
                state.last_error = status
        except Exception as exc:
            state.last_error = str(exc)[:100] if isinstance(exc, ValueError) else type(exc).__name__
            logger.warning("Article snapshot not confirmed: error_type=%s", type(exc).__name__)
        await db.commit()
    return created


async def monitor_sources(source_urls: Sequence[str] | None = None) -> list[LawChange]:
    urls = list(settings.law_change_source_list() if source_urls is None else source_urls)
    curated_file = settings.LAW_CHANGE_CURATED_FILE.strip()
    if not curated_file:
        default_feed = Path(settings.RAG_DOCS_PATH) / "reviewed_changes.json"
        curated_file = str(default_feed) if default_feed.is_file() else ""
    if not urls and not curated_file:
        logger.warning("Law monitoring skipped: no sources configured")
        return []

    timeout = httpx.Timeout(settings.LAW_CHANGE_HTTP_TIMEOUT, connect=10.0)
    created: list[LawChange] = []
    # Retry only connection establishment for these read-only source requests.
    # HTTP errors and parsing failures are not retried by this transport.
    transport = httpx.AsyncHTTPTransport(retries=2)
    async with httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=timeout,
                                follow_redirects=True, transport=transport) as client:
        async with AsyncSessionLocal() as db:
            if curated_file:
                try:
                    parsed = load_curated_changes(Path(curated_file), catalog_root=Path(settings.RAG_DOCS_PATH))
                except CuratedSourceError as exc:
                    logger.warning("Curated law source rejected: %s", exc)
                else:
                    # Reviewed feed runs first: a matching overview must not consume
                    # the duplicate identity before its explicit affected norms arrive.
                    created.extend(await persist_parsed_changes(db, parsed))
            known_sources = (await db.execute(select(ChatLawReference.source_url, ChatLawReference.document_key).distinct())).all() if urls else []
            candidates = {}
            for url, key in known_sources:
                doc_id = consultant_document_id(url)
                if doc_id:
                    candidates.setdefault(doc_id, set()).add(key)
            document_keys = {doc_id: next(iter(values)) for doc_id, values in candidates.items() if len(values) == 1}
            for source_url in urls:
                state = await db.scalar(select(LawMonitorState).where(LawMonitorState.source_url == source_url))
                if state is None:
                    state = LawMonitorState(source_url=source_url, progress={}, coverage_gap=False)
                    db.add(state)
                    await db.flush()
                state.last_attempt_at = datetime.now(timezone.utc)
                progress = dict(state.progress or {})
                try:
                    parsed = await collect_changes_from_source(client, source_url, document_keys=document_keys,
                        checkpoint=state.progress, progress=progress)
                    created.extend(await persist_parsed_changes(db, parsed))
                    earliest = progress.get("earliest_available_start")
                    previous_coverage = (state.progress or {}).get("coverage_through")
                    if earliest and (previous_coverage or state.last_success_at):
                        previous_end = datetime.fromisoformat(previous_coverage).date() if previous_coverage else state.last_success_at.date()
                        allowance = 3 if previous_coverage else 8
                        if datetime.fromisoformat(earliest).date() > previous_end + timedelta(days=allowance):
                            state.coverage_gap = True
                            logger.warning("Source recovery exceeds available archive; coverage gap recorded")
                    state.progress = progress
                    if progress.get("source_success"):
                        state.last_success_at = datetime.now(timezone.utc)
                        state.last_error = None
                    else:
                        state.last_error = "IncompleteSourceCheck"
                    await db.commit()
                except Exception as exc:
                    await db.rollback()
                    state = await db.scalar(select(LawMonitorState).where(LawMonitorState.source_url == source_url))
                    if state is None:
                        state = LawMonitorState(source_url=source_url, progress={}, coverage_gap=False)
                        db.add(state)
                    state.last_attempt_at = datetime.now(timezone.utc)
                    state.last_error = type(exc).__name__[:100]
                    await db.commit()
                    logger.warning("Law source failed; checkpoint retained: error_type=%s", type(exc).__name__)
            if urls:
                await retry_pending_norms(db, client, document_keys)
                created.extend(await refresh_tracked_article_snapshots(db, client, known_sources))
    return created
