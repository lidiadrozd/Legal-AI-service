from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from typing import Any
from urllib.parse import urljoin, urlparse

CONSULTANT_UPDPROF_PATH = "/law/review/fed/updprof/"
CONSULTANT_PERIOD_RE = re.compile(
    r'href="(?P<path>/document/cons_doc_LAW_33770/[a-f0-9]{40}/)#dst1"',
    re.IGNORECASE,
)
CONSULTANT_TOC_LINK_RE = re.compile(
    r'<div class="document-page__toc">\s*<ul>(?P<body>.*?)</ul>',
    re.IGNORECASE | re.DOTALL,
)
CONSULTANT_HREF_RE = re.compile(
    r'href="(?P<path>/document/cons_doc_LAW_33770/[a-f0-9]{40}/)"[^>]*>(?P<label>[^<]+)</a>',
    re.IGNORECASE,
)
CONSULTANT_CONTENT_RE = re.compile(
    r'<div class="document-page__content[^"]*">(?P<body>.*?)</div>\s*<div class="document-page__toc">',
    re.IGNORECASE | re.DOTALL,
)
CONSULTANT_PARAGRAPH_RE = re.compile(r"<p[^>]*>(?P<body>.*?)</p>", re.IGNORECASE | re.DOTALL)
CONSULTANT_LINK_RE = re.compile(
    r'href="(?P<href>/document/cons_doc_LAW_\d+/?[^"]*)"',
    re.IGNORECASE,
)
CONSULTANT_DATE_RE = re.compile(
    r"\(ред\.\s*от\s*(\d{2}\.\d{2}\.\d{4})(?:,\s*с изм\.\s*от\s*(\d{2}\.\d{2}\.\d{4}))?\)",
    re.IGNORECASE,
)
CONSULTANT_LAW_NUMBER_RE = re.compile(
    r"от\s+(\d{2}\.\d{2}\.\d{4})\s+N\s+([\d]+-ФЗ)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedLawChange:
    title: str
    change_date: datetime | None
    description: str
    source_url: str
    document_number: str | None = None
    document_title: str | None = None
    category: str | None = None


def _strip_tags(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_ru_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%d.%m.%Y")
    except ValueError:
        return None


def _normalize_url(base_url: str, path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return urljoin(base_url, path)


def is_consultant_source(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.netloc.endswith("consultant.ru")


def is_consultant_index(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.netloc.endswith("consultant.ru") and CONSULTANT_UPDPROF_PATH in parsed.path


def parse_json_changes(payload: Any, source_url: str) -> list[ParsedLawChange]:
    if not isinstance(payload, dict):
        return []
    raw_changes = payload.get("changes")
    if not isinstance(raw_changes, list):
        return []

    parsed: list[ParsedLawChange] = []
    for item in raw_changes:
        if not isinstance(item, dict):
            continue
        title = _strip_tags(str(item.get("title") or "")).strip()
        if not title:
            continue
        description = _strip_tags(str(item.get("description") or item.get("text") or "")).strip()
        change_date = None
        raw_date = item.get("date")
        if isinstance(raw_date, str):
            try:
                change_date = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            except ValueError:
                change_date = _parse_ru_date(raw_date)
        link = str(item.get("url") or item.get("source_url") or source_url).strip()
        parsed.append(
            ParsedLawChange(
                title=title,
                change_date=change_date,
                description=description or "Описание изменения не предоставлено источником.",
                source_url=link,
                document_number=(str(item.get("document_number")).strip() if item.get("document_number") else None),
                document_title=(str(item.get("document_title")).strip() if item.get("document_title") else None),
                category=(str(item.get("category")).strip() if item.get("category") else None),
            )
        )
    return parsed


def parse_consultant_index(html: str, base_url: str) -> str | None:
    match = CONSULTANT_PERIOD_RE.search(html)
    if not match:
        return None
    return _normalize_url(base_url, match.group("path"))


def parse_consultant_period_categories(html: str, base_url: str) -> list[tuple[str, str]]:
    toc_match = CONSULTANT_TOC_LINK_RE.search(html)
    if not toc_match:
        return []
    links: list[tuple[str, str]] = []
    seen: set[str] = set()
    for match in CONSULTANT_HREF_RE.finditer(toc_match.group("body")):
        label = _strip_tags(match.group("label"))
        path = match.group("path")
        if not label or label.lower().startswith("с "):
            continue
        if path in seen:
            continue
        seen.add(path)
        links.append((label, _normalize_url(base_url, path)))
    return links


def _extract_content_paragraphs(html: str) -> list[tuple[str, str]]:
    content_match = CONSULTANT_CONTENT_RE.search(html)
    body = content_match.group("body") if content_match else html
    paragraphs: list[tuple[str, str]] = []
    for match in CONSULTANT_PARAGRAPH_RE.finditer(body):
        raw = match.group("body")
        text = _strip_tags(raw)
        if text:
            paragraphs.append((raw, text))
    return paragraphs


def parse_consultant_category(html: str, page_url: str, category: str | None = None) -> list[ParsedLawChange]:
    paragraphs = _extract_content_paragraphs(html)
    if not paragraphs:
        return []

    parsed: list[ParsedLawChange] = []
    block_raw: list[str] = []
    block_text: list[str] = []

    def flush_block() -> None:
        if not block_text:
            block_raw.clear()
            return
        text = " ".join(block_text).strip()
        raw = " ".join(block_raw)
        block_raw.clear()
        block_text.clear()
        if "фз" not in text.lower():
            return
        law_number_match = CONSULTANT_LAW_NUMBER_RE.search(text)
        date_match = CONSULTANT_DATE_RE.search(text)
        quoted = re.findall(r"«([^»]+)»|\"([^\"]+)\"", text)
        quoted_title = next((left or right for left, right in quoted if (left or right)), "")
        title = quoted_title.strip() or text[:240]
        document_number = law_number_match.group(2) if law_number_match else None
        change_date = _parse_ru_date(
            date_match.group(2)
            if date_match and date_match.group(2)
            else (date_match.group(1) if date_match else None)
        )
        link_match = CONSULTANT_LINK_RE.search(raw)
        source_url = _normalize_url(page_url, link_match.group("href")) if link_match else page_url
        parsed.append(
            ParsedLawChange(
                title=title,
                change_date=change_date,
                description=text,
                source_url=source_url,
                document_number=document_number,
                document_title=title,
                category=category,
            )
        )

    for raw, text in paragraphs:
        if text.lower().startswith("федеральный") and CONSULTANT_LAW_NUMBER_RE.search(text):
            flush_block()
            block_raw.append(raw)
            block_text.append(text)
            continue
        if block_text:
            block_raw.append(raw)
            block_text.append(text)
            if re.search(r"«[^»]+»|\"[^\"]+\"", text):
                flush_block()

    flush_block()
    return parsed


def parse_payload(raw_text: str, source_url: str, content_type: str | None = None) -> list[ParsedLawChange]:
    stripped = (raw_text or "").strip()
    if not stripped:
        return []
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            return parse_json_changes(payload, source_url)
        if isinstance(payload, list):
            return parse_json_changes({"changes": payload}, source_url)
    if is_consultant_source(source_url):
        if is_consultant_index(source_url):
            return []
        if parse_consultant_period_categories(stripped, source_url):
            return []
        return parse_consultant_category(stripped, source_url)
    return []
