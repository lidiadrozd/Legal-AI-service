from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse
from app.services.legal_sources import NormIdentity
from app.services.answer_norms import heading_document_key

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
    r'href="(?P<href>(?:https://(?:www\.)?consultant\.ru)?/document/cons_doc_LAW_\d+/?[^"]*)"',
    re.IGNORECASE,
)
CONSULTANT_DATE_RE = re.compile(
    r"\(ред\.\s*от\s*(\d{2}\.\d{2}\.\d{4})(?:,\s*с изм\.\s*от\s*(\d{2}\.\d{2}\.\d{4}))?\)",
    re.IGNORECASE,
)
CONSULTANT_LAW_NUMBER_RE = re.compile(
    r"от\s+(\d{2}\.\d{2}\.\d{4})\s+N\s+([\d]+(?:-ФЗ|-ФКЗ|-\d+)?)",
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
    affected_norms: tuple[NormIdentity, ...] = ()
    old_version: str | None = None
    new_version: str | None = None
    amendment_source_urls: tuple[str, ...] = ()
    norm_evidence: tuple[dict, ...] = ()
    document_key: str | None = None
    norm_resolution_pending: bool = False
    scope_resolution: dict | None = None


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
    return (parsed.hostname or "").lower() in {"consultant.ru", "www.consultant.ru"}


def is_consultant_index(url: str) -> bool:
    parsed = urlparse(url)
    return (parsed.hostname or "").lower() in {"consultant.ru", "www.consultant.ru"} and CONSULTANT_UPDPROF_PATH in parsed.path


def _revision_text(value: Any) -> str | None:
    # Keep paragraph boundaries; structured values are not legal text.
    if not isinstance(value, str):
        return None
    return value.strip() or None


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
        affected_norms = []
        raw_norms = item.get("affected_norms", [])
        if isinstance(raw_norms, list):
            for raw_norm in raw_norms:
                try:
                    affected_norms.append(NormIdentity.from_dict(raw_norm))
                except ValueError:
                    continue
        parsed.append(
            ParsedLawChange(
                title=title,
                change_date=change_date,
                description=description or "Описание изменения не предоставлено источником.",
                source_url=link,
                document_number=(str(item.get("document_number")).strip() if item.get("document_number") else None),
                document_title=(str(item.get("document_title")).strip() if item.get("document_title") else None),
                category=(str(item.get("category")).strip() if item.get("category") else None),
                affected_norms=tuple(affected_norms),
                old_version=_revision_text(item.get("old_version")),
                new_version=_revision_text(item.get("new_version")),
            )
        )
    return parsed


class _PeriodLinks(HTMLParser):
    def __init__(self, base_url):
        super().__init__()
        self.base_url, self.links, self.seen = base_url, [], set()
        self.href, self.label = None, []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.href = dict(attrs).get("href")
            self.label = []

    def handle_data(self, data):
        if self.href:
            self.label.append(data)

    def handle_endtag(self, tag):
        if tag != "a" or not self.href:
            return
        label = " ".join("".join(self.label).split())
        url = urljoin(self.base_url, self.href).split("#", 1)[0]
        parsed = urlparse(url)
        if (parsed.scheme == "https" and is_consultant_source(url)
                and re.fullmatch(r"/document/cons_doc_LAW_33770/[a-f0-9]{40}/", parsed.path, re.I)
                and re.match(r"^с\s+\d", label, re.I) and url not in self.seen):
            self.links.append((label, url))
            self.seen.add(url)
        self.href = None


def parse_consultant_periods(html: str, base_url: str) -> list[tuple[str, str]]:
    parser = _PeriodLinks(base_url)
    parser.feed(html)
    return parser.links


def consultant_period_dates(label):
    months = {name: index for index, name in enumerate(("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"), 1)}
    month = "|".join(months)
    match = re.fullmatch(rf"с\s+(\d{{1,2}})(?:\s+({month}))?(?:\s+(\d{{4}}))?\s+по\s+(\d{{1,2}})\s+({month})\s+(\d{{4}})\s+года", label, re.I)
    if not match:
        return None
    day, start_month, start_year, end_day, end_month, end_year = match.groups()
    end_month_num = months[end_month.lower()]
    start_month_num = months[start_month.lower()] if start_month else end_month_num
    end_year_num = int(end_year)
    start_year_num = int(start_year) if start_year else end_year_num - (start_month_num > end_month_num)
    try:
        start = datetime(start_year_num, start_month_num, int(day))
        end = datetime(end_year_num, end_month_num, int(end_day))
    except ValueError:
        return None
    return (start, end) if start <= end else None


def parse_consultant_index(html: str, base_url: str) -> str | None:
    periods = parse_consultant_periods(html, base_url)
    return periods[0][1] if periods else None


class _TocLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.div_depth = 0
        self.href = None
        self.label = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "div":
            if self.div_depth:
                self.div_depth += 1
            elif "document-page__toc" in attrs.get("class", "").split():
                self.div_depth = 1
        if tag == "a" and self.div_depth:
            self.href, self.label = attrs.get("href"), []

    def handle_data(self, data):
        if self.href:
            self.label.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.href:
            self.links.append((" ".join("".join(self.label).split()), self.href))
            self.href = None
        if tag == "div" and self.div_depth:
            self.div_depth -= 1


def parse_consultant_period_categories(html: str, base_url: str) -> list[tuple[str, str]]:
    parser = _TocLinks()
    parser.feed(html)
    links = []
    seen = set()
    has_period_groups = any(re.match(r"^с\s+\d", label, re.I) for label, _ in parser.links)
    selected = base_url.split("#", 1)[0]
    current_period = None
    for label, path in parser.links:
        url = urljoin(base_url, path).split("#", 1)[0]
        if re.match(r"^с\s+\d", label, re.I):
            current_period = url
            continue
        if has_period_groups and current_period != selected:
            continue
        if (label and is_consultant_source(url)
                and re.fullmatch(r"/document/cons_doc_LAW_33770/[a-f0-9]{40}/", urlparse(url).path, re.I)
                and url not in seen):
            seen.add(url)
            links.append((label, url))
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
        raw_paragraphs = list(block_raw)
        raw = " ".join(raw_paragraphs)
        block_raw.clear()
        block_text.clear()
        law_number_match = CONSULTANT_LAW_NUMBER_RE.search(text)
        if law_number_match is None:
            return
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
        # Only the heading identifies the original law. Later links may name
        # the amending act; never substitute one of them for the original.
        heading = raw_paragraphs[0]
        link_match = CONSULTANT_LINK_RE.search(heading)
        source_url = _normalize_url(page_url, link_match.group("href")) if link_match else page_url
        if not link_match:
            for attribute in re.finditer(r'data-document-link="([^\"]*)"', heading):
                try:
                    document = json.loads(unescape(attribute.group(1)))
                except (ValueError, TypeError):
                    continue
                if (isinstance(document, dict) and document.get("type") in {"editions", "document"}
                        and document.get("base") == "LAW"
                        and type(document.get("num")) is int
                        and 0 < document["num"] < 10**12):
                    source_url = _normalize_url(page_url, f"/document/cons_doc_LAW_{document['num']}/")
                    break
        amendment_urls = []
        # Keep separate the original document link and links explicitly named as
        # amending acts. Unrelated entry-into-force and sidebar links are ignored.
        for paragraph_raw in raw_paragraphs:
            paragraph_text = _strip_tags(paragraph_raw)
            if re.search(r"(?:изменения,?\s*внесенные|с\s+изм\.,?\s*внесенными)", paragraph_text, re.I):
                for match in re.finditer(r'<a[^>]*href="(?P<href>(?:https://(?:www\.)?consultant\.ru)?/document/cons_doc_LAW_\d+/[^"]*)"[^>]*>(?P<label>.*?)</a>', paragraph_raw, re.I | re.S):
                    if _strip_tags(match.group("label")).casefold().startswith(("законом", "законами")):
                        amendment_urls.append(_normalize_url(page_url, match.group("href")))
        parsed.append(
            ParsedLawChange(
                title=title,
                change_date=change_date,
                description=text,
                source_url=source_url,
                document_number=document_number,
                document_title=title,
                category=category,
                amendment_source_urls=tuple(dict.fromkeys(amendment_urls)),
                document_key=heading_document_key(_strip_tags(raw_paragraphs[0])),
            )
        )

    for raw, text in paragraphs:
        if (text.casefold().startswith(("федеральный", '"', "«"))
                and CONSULTANT_LAW_NUMBER_RE.search(text)):
            flush_block()
            block_raw.append(raw)
            block_text.append(text)
            continue
        if block_text:
            block_raw.append(raw)
            block_text.append(text)

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
