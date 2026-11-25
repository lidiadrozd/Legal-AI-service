"""Resolve registered Russian statutes through ConsultantPlus' table of contents."""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from time import monotonic
from urllib.parse import urldefrag, urljoin, urlsplit

import httpx

from app.services.answer_norms import ARTICLE, CODE_NAMES, CODE_URLS, GK_KEY, NK_FIRST, TK_KEY, extract_answer_norms
from app.services.article_change_detection import build_article_snapshot
from app.services.consultant_norm_changes import _Paragraphs, consultant_document_id
from app.services.law_change_parser import _TocLinks
from app.services.legal_sources import NormIdentity

logger = logging.getLogger(__name__)
_HEADING = re.compile(r"\bСтатья\s+(\d+(?:\.\d+)*)(?=\.|\s|$)", re.I)
_ARTICLE_TITLE = re.compile(r"^(?:(?:ТК|ГК) РФ\s+)?Статья\s+(\d+(?:\.\d+)*)(?=\.|\s|$)", re.I)
_NOTE = re.compile(
    r"^(?:\(|КонсультантПлюс|Путеводител[ьи]|Перспективы и риски|"
    r"Готовое решение|Вопросы применения|См\.\s|Открыть полный текст|"
    r"Ситуации, связанные|Судебная практика|Подборка судебных решений)", re.I,
)
_STOP_WORDS = {"это", "что", "как", "мне", "могу", "для", "при", "или", "какой", "какие",
               "статья", "статье", "согласно", "кодекс", "кодексу", "считается"}
_PAGE_CACHE: dict[str, tuple[float, str]] = {}


@dataclass(frozen=True)
class ArticleQuote:
    norm: NormIdentity
    text: str
    excerpt: str
    source_url: str
    revision: str


class _Headings(HTMLParser):
    """Article titles can sit outside document-page__content."""

    def __init__(self):
        super().__init__()
        self.tag = None
        self.parts = []
        self.titles = []

    def handle_starttag(self, tag, attrs):
        if tag in {"h1", "h2", "title"}:
            self.tag, self.parts = tag, []

    def handle_data(self, data):
        if self.tag:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == self.tag:
            self.titles.append(" ".join("".join(self.parts).split()))
            self.tag = None


class _StatuteParagraphs(_Paragraphs):
    """Keep notification parser's content boundaries and omit editorial inserts."""

    def __init__(self):
        super().__init__()
        self.insert_depth = 0

    def handle_starttag(self, tag, attrs):
        classes = dict(attrs).get("class", "").split()
        if tag == "div" and (self.insert_depth or any(
            value.startswith(("document-page__insert", "document-page__note")) for value in classes
        )):
            self.insert_depth += 1
        if not self.insert_depth:
            super().handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if self.insert_depth:
            if tag == "div":
                self.insert_depth -= 1
        else:
            super().handle_endtag(tag)

    def handle_data(self, data):
        if not self.insert_depth:
            super().handle_data(data)


def _terms(text):
    return {word[:4] if len(word) >= 5 else word
            for word in re.findall(r"[а-яё]+|\d+", text.casefold())
            if (len(word) >= 3 or word.isdigit()) and word not in _STOP_WORDS}


def best_excerpt(body: str, query: str) -> str:
    """Choose an intact sentence from a statute paragraph after removing its heading."""
    candidates = []
    for line in body.splitlines():
        if _NOTE.match(line):
            continue
        for sentence in re.split(r"(?<=[.!?])\s+(?=[А-ЯЁ«])", line):
            if 12 <= len(sentence) <= 900 and sentence.endswith((".", "!", "?", ";")):
                candidates.append(sentence)
    if not candidates:
        return ""
    terms = _terms(query)
    def score(sentence):
        words = _terms(sentence)
        return len(words & terms) / max(1, len(words)) ** 0.5
    return max(candidates, key=score)


def _detail_body(html: str, article: str) -> str:
    content = _StatuteParagraphs()
    content.feed(html)
    if content.content_depth is not None:
        return ""
    body = [" ".join(p["text"].split()) for p in content.paragraphs]
    # Some layouts put the heading in the first content paragraph, some in h1.
    headings = [(i, match[1]) for i, line in enumerate(body)
                if (match := _ARTICLE_TITLE.match(line))]
    if headings:
        if len(headings) != 1 or headings[0][1] != article:
            return ""
        body = body[headings[0][0] + 1:]
    else:
        titles = _Headings()
        titles.feed(html)
        if {match[1] for title in titles.titles if (match := _HEADING.search(title))} != {article}:
            return ""
    return "\n".join(line for line in body if line and not _NOTE.match(line))


async def _page(client, url):
    cached = _PAGE_CACHE.get(url)
    if cached and monotonic() - cached[0] < 900:
        return cached[1]
    response = await client.get(url)
    response.raise_for_status()
    html = response.text
    if len(_PAGE_CACHE) >= 64:
        del _PAGE_CACHE[next(iter(_PAGE_CACHE))]
    _PAGE_CACHE[url] = (monotonic(), html)
    return html


def _article_links(html, root):
    toc = _TocLinks()
    toc.feed(html)
    links = {}
    for label, href in toc.links:
        match = _ARTICLE_TITLE.match(label)
        if not match:
            continue
        url = urldefrag(urljoin(root, href)).url
        target = urlsplit(url)
        if (consultant_document_id(url) == consultant_document_id(root)
                and target.path != urlsplit(root).path and not target.query):
            links[match[1]] = (label[match.end():].lstrip(". "), url)
    return links


async def _document_quotes(client, key, numbers, query):
    root = CODE_URLS[key]
    html = await _page(client, root)
    links = _article_links(html, root)
    # The notification parser also supports editions published as a single page.
    snapshot = None if links else build_article_snapshot(html, root, key)

    async def read(number):
        if number in links:
            _, url = links[number]
            body = _detail_body(await _page(client, url), number)
            revision = "live"
        elif snapshot and number in snapshot["articles"]:
            url = root
            text = snapshot["articles"][number]["text"]
            body = text.partition("\n")[2]
            revision = snapshot.get("revision_date") or "live"
        else:
            return None
        excerpt = best_excerpt(body, query)
        if excerpt:
            return ArticleQuote(NormIdentity(key, number), body, excerpt, url, revision)
        return None

    results = await asyncio.gather(*(read(number) for number in numbers), return_exceptions=True)
    return [item for item in results if isinstance(item, ArticleQuote)]


async def find_article_quotes(query: str, norms: list[NormIdentity]) -> list[ArticleQuote]:
    documents: dict[str, list[str]] = {}
    for norm in norms:
        if not norm.article or norm.document_key not in CODE_URLS:
            continue
        if norm.document_key not in documents and len(documents) >= 2:
            continue
        numbers = documents.setdefault(norm.document_key, [])
        if norm.article not in numbers:
            numbers.append(norm.article)
        if sum(map(len, documents.values())) >= 4:
            break
    if not documents:
        return []
    # Server-side direct GETs, independent of the model connection and browser VPN.
    async with httpx.AsyncClient(timeout=httpx.Timeout(4, connect=2), trust_env=False) as client:
        jobs = (asyncio.wait_for(_document_quotes(client, key, numbers, query), 8)
                for key, numbers in documents.items())
        results = await asyncio.gather(*jobs, return_exceptions=True)
    quotes = []
    for result in results:
        if isinstance(result, list):
            quotes.extend(result)
        elif isinstance(result, Exception):
            logger.info("ConsultantPlus article lookup unavailable (%s)", type(result).__name__)
    return quotes


async def find_question_quotes(query: str) -> list[ArticleQuote]:
    """Return independently identifiable statute text when the model is offline."""
    explicit = [item["legal_source"].norm for item in extract_answer_norms(query)
                if item["legal_source"].norm.article]
    if explicit:
        if re.search(r"процитируй|цитат\w*\s+(?:из\s+)?стать|(?:текст|содержание)\s+стать", query, re.I):
            return await find_article_quotes(query, explicit)
        # Without a semantic review an article suggested by the user cannot
        # establish that it governs their situation.
        return []
    named = [(pattern, key) for pattern, key in CODE_NAMES if re.search(pattern, query, re.I)]
    if len(named) != 1 or re.search(ARTICLE, query, re.I):
        return []
    pattern, key = named[0]
    # The name of a multipart code alone doesn't identify its volume.
    if key in {GK_KEY, NK_FIRST}:
        return []
    terms = _terms(re.sub(pattern, "", query, flags=re.I))
    if len(terms) < 2:
        return []
    root = CODE_URLS[key]
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(4, connect=2), trust_env=False) as client:
            html = await asyncio.wait_for(_page(client, root), 4)
    except (httpx.HTTPError, OSError, asyncio.TimeoutError):
        return []
    candidates = []
    for number, (title, _) in _article_links(html, root).items():
        title_terms = _terms(title)
        if terms <= title_terms and len(terms) * 3 >= len(title_terms) * 2:
            candidates.append((len(title_terms), number))
    candidates.sort()
    if not candidates or (len(candidates) > 1 and candidates[0][0] == candidates[1][0]):
        return []
    return await find_article_quotes(query, [NormIdentity(key, candidates[0][1])])


def _basis_topic(query):
    # Expand everyday words used in questions into terms used in statute headings.
    words = _terms(query.replace("ё", "е"))
    if re.search(r"сведени|информаци|данны[ехм]", query, re.I) and re.search(
        r"обо мне|о себе|личн|персональн|неполн|неверн|исправ", query, re.I
    ):
        words.update(_terms("персональные данные"))
    settlement = bool(re.search(r"увол|уволь|прекращени\w*\s+трудов", query, re.I)
                      and re.search(r"выплат|компенсац|расч[её]т|заплат", query, re.I)
                      and re.search(r"срок|когда|день|дней|момент|поздн", query, re.I))
    if settlement:
        words.update(_terms("сроки расчета при увольнении"))
    return words, settlement


async def find_basis_candidates(query: str, draft_answer: str, offered=()) -> list[ArticleQuote]:
    """Fetch cited hypotheses and independent title matches for the legal review."""
    context = query + "\n" + draft_answer
    documents = {}
    for item in (*extract_answer_norms(query), *extract_answer_norms(draft_answer), *offered):
        source = item.get("legal_source")
        norm = getattr(source, "norm", None)
        if norm and norm.document_key in CODE_URLS:
            numbers = documents.setdefault(norm.document_key, [])
            if norm.article and norm.article not in numbers:
                numbers.append(norm.article)
    for pattern, key in CODE_NAMES:
        if re.search(pattern, context, re.I):
            documents.setdefault(key, [])
    terms, settlement = _basis_topic(query)
    if settlement or re.search(r"работодател|работник|трудов\w*\s+(?:книжк|договор)|увольнен", query, re.I):
        documents.setdefault(TK_KEY, [])
    if not documents:
        return []

    async def search(client, key, explicit):
        root = CODE_URLS[key]
        html = await _page(client, root)
        links = _article_links(html, root)
        titles = {number: title for number, (title, _) in links.items()}
        if not titles:
            articles = build_article_snapshot(html, root, key)["articles"]
            titles = {number: entry["text"].partition("\n")[0] for number, entry in articles.items()}
        ranked = []
        for number, title in titles.items():
            title_words = _terms(title.casefold().replace("ё", "е"))
            overlap = terms & title_words
            if overlap - {"рабо", "прав", "стат"}:
                score = len(overlap) / max(1, len(title_words)) ** 0.5
                ranked.append((score, number))
        ranked.sort(key=lambda item: -item[0])
        numbers = list(explicit[:3])
        if key == TK_KEY and settlement and "140" in titles:
            numbers.append("140")
        numbers.extend(number for _, number in ranked if number not in numbers)
        return await _document_quotes(client, key, list(dict.fromkeys(numbers))[:6], query)

    async with httpx.AsyncClient(timeout=httpx.Timeout(4, connect=2), trust_env=False) as client:
        jobs = [asyncio.wait_for(search(client, key, numbers), 8)
                for key, numbers in list(documents.items())[:3]]
        results = await asyncio.gather(*jobs, return_exceptions=True)
    quotes = []
    for result in results:
        if isinstance(result, list):
            quotes.extend(result)
        elif isinstance(result, Exception):
            logger.info("ConsultantPlus candidate lookup unavailable (%s)", type(result).__name__)
    return quotes
