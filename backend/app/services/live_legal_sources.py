"""Adapt ConsultantPlus statute quotations to the chat's trusted evidence format."""
from __future__ import annotations

import hashlib
import re

from app.services.answer_norms import document_label, extract_answer_norms
from app.services.consultant_article_quotes import find_article_quotes
from app.services.legal_sources import LegalSource, NormIdentity

def _next_citation_id(existing: list[dict]) -> int:
    values = []
    for item in existing:
        if not isinstance(item, dict):
            continue
        value = item.get("citation_id")
        if isinstance(value, bool):
            continue
        if isinstance(value, int) and value > 0:
            values.append(value)
        elif isinstance(value, str) and value.isdecimal() and int(value) > 0:
            values.append(int(value))
    return max(values, default=0) + 1


async def resolve_live_legal_sources(
    user_query: str,
    draft_answer: str,
    existing: list[dict] | None = None,
) -> list[dict]:
    existing = existing or []
    cited = [item["legal_source"].norm for item in extract_answer_norms(draft_answer or "")]
    markers = set(re.findall(r"\[Источник\s+(\d+)\]", draft_answer or ""))
    verified, reusable_ids = set(), {}
    for item in existing:
        source = item.get("legal_source")
        if not isinstance(source, LegalSource) or not source.norm.article:
            continue
        article = NormIdentity(source.norm.document_key, source.norm.article)
        if source.has_verified_excerpt:
            verified.add(article)
        elif item.get("citation_id") is not None:
            reusable_ids.setdefault(article, item["citation_id"])
            if str(item["citation_id"]) in markers:
                cited.append(article)

    norms = [norm for norm in cited if NormIdentity(norm.document_key, norm.article) not in verified]
    quotes = await find_article_quotes(user_query, norms)
    result = []
    next_id = _next_citation_id(existing)
    for quote in quotes:
        marker = reusable_ids.get(quote.norm)
        if marker is None:
            marker, next_id = next_id, next_id + 1
        result.append({
            "citation_id": marker,
            "legal_source": LegalSource(
                norm=quote.norm, source_url=quote.source_url, revision=quote.revision,
                sha256=hashlib.sha256(quote.text.encode("utf-8")).hexdigest(),
                content_kind="statute_text", verbatim_excerpt=quote.excerpt,
            ),
            "text": quote.text,
            "origin": "live_source",
        })
    return result

def format_live_legal_sources(items: list[dict]) -> str:
    """Render fetched items in the same trusted-evidence style as local RAG."""
    blocks = []
    for item in items or []:
        source = item.get("legal_source") if isinstance(item, dict) else None
        if not isinstance(source, LegalSource) or not source.has_verified_excerpt:
            continue
        norm = source.norm
        scope = f"{document_label(norm.document_key)}, \u0441\u0442\u0430\u0442\u044c\u044f {norm.article}"
        if norm.part:
            scope += f", \u0447\u0430\u0441\u0442\u044c {norm.part}"
        if norm.point:
            scope += f", \u043f\u0443\u043d\u043a\u0442 {norm.point}"
        blocks.append(
            f"[\u0418\u0441\u0442\u043e\u0447\u043d\u0438\u043a {item.get('citation_id')}] {scope}\n"
            f"\u0420\u0435\u0434\u0430\u043a\u0446\u0438\u044f: {source.revision}; \u0441\u0441\u044b\u043b\u043a\u0430: {source.source_url}\n"
            "\u0412\u0435\u0440\u0438\u0444\u0438\u0446\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u0430\u044f \u0434\u043e\u0441\u043b\u043e\u0432\u043d\u0430\u044f \u0446\u0438\u0442\u0430\u0442\u0430 "
            f"(\u0438\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0439 \u0442\u043e\u043b\u044c\u043a\u043e \u0435\u0451 \u0432 \u043a\u0430\u0432\u044b\u0447\u043a\u0430\u0445): \u00ab{source.verbatim_excerpt}\u00bb"
        )
    return "\n\n".join(blocks)

