"""Extract explicit linked amendment targets, not mentions of laws in inserted text."""
from dataclasses import dataclass
from html.parser import HTMLParser
import re
from urllib.parse import urlparse, urljoin
import hashlib

from app.services.legal_sources import NormIdentity
from app.services.answer_norms import heading_document_key

DOC_PATH = re.compile(r"^/document/cons_doc_LAW_(\d+)/(?:[a-f0-9]{40}/)?$", re.I)
SCOPE = re.compile(r"^(?:в\s+)?(?:(?:пункт|пункта|пункте)\s+(?P<point>\d+(?:\.\d+)*)\s+)?"
                   r"(?:(?:часть|части|частью)\s+(?P<part>\d+(?:\.\d+)*)\s+)?"
                   r"(?:статья|статьи|статье|статью|статьей|статьях)\s+(?P<articles>[\d.,\sи–-]+)$", re.I)


def parse_scope_label(label):
    match = SCOPE.fullmatch(" ".join(label.split()).strip())
    if not match:
        return []
    articles = []
    for item in re.split(r"\s*(?:,|\bи\b)\s*", match["articles"].strip()):
        if re.fullmatch(r"\d+(?:\.\d+)*", item):
            articles.append(item)
        elif re.fullmatch(r"\d+\s*[-–]\s*\d+", item):
            low, high = map(int, re.split(r"\s*[-–]\s*", item))
            if high < low or high-low > 100:
                return []
            articles.extend(map(str, range(low, high+1)))
        else:
            return []
    if len(articles) > 100 or (len(articles) > 1 and (match["part"] or match["point"])):
        return []
    return [{"article": article, "part": match["part"] or "", "point": match["point"] or ""}
            for article in dict.fromkeys(articles)]

ACTION = re.compile(r"\b(?:изложить|дополнить|заменить|исключить)\b|"
                    r"признать\s+утративш\w*\s+силу|следующие\s+изменения", re.I)
PREFIX = re.compile(r"^(?:\d+[).]\s*)?(?:в|внести\s+в)?\s*$", re.I)


def consultant_document_id(url):
    try:
        parsed = urlparse(url)
        if parsed.scheme != "https" or (parsed.hostname or "").lower() not in {"consultant.ru", "www.consultant.ru"}:
            return None
        if parsed.username or parsed.password or parsed.port not in {None, 443}:
            return None
        match = DOC_PATH.fullmatch(parsed.path)
        return match.group(1) if match else None
    except ValueError:
        return None


def catalog_document_keys(catalog):
    candidates = {}
    for source in catalog.values():
        doc_id = consultant_document_id(source.source_url)
        if doc_id:
            candidates.setdefault(doc_id, set()).add(source.norm.document_key)
    return {doc_id: next(iter(keys)) for doc_id, keys in candidates.items() if len(keys) == 1}


class _Paragraphs(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.content_depth = None
        self.current = None
        self.anchor = None
        self.paragraphs = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "div":
            self.depth += 1
            if self.content_depth is None and "document-page__content" in values.get("class", "").split():
                self.content_depth = self.depth
        if self.content_depth is None:
            return
        if tag == "p":
            self.current = {"text": "", "links": []}
        elif tag == "a" and self.current is not None:
            self.anchor = {"href": values.get("href", ""), "label": "", "start": len(self.current["text"])}

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"] += data
            if self.anchor is not None:
                self.anchor["label"] += data

    def handle_endtag(self, tag):
        if tag == "a" and self.anchor is not None and self.current is not None:
            self.current["links"].append(self.anchor)
            self.anchor = None
        elif tag == "p" and self.current is not None:
            self.paragraphs.append(self.current)
            self.current = None
            self.anchor = None
        elif tag == "div":
            if self.depth == self.content_depth:
                self.content_depth = None
                self.current = None
            self.depth -= 1


@dataclass(frozen=True)
class ConfirmedNormChange:
    norm: NormIdentity
    evidence: dict


def _target_candidates(html, publication_url):
    if not consultant_document_id(publication_url):
        return []
    parser = _Paragraphs()
    parser.feed(html)
    candidates = []
    quote_state = None
    for paragraph in parser.paragraphs:
        quoted_before = quote_state is not None
        instruction, quote_state = _outside_quotes(paragraph["text"], quote_state)
        if quoted_before:
            continue
        for link in paragraph["links"]:
            label = " ".join(link["label"].split()).strip()
            scopes = parse_scope_label(label)
            if not scopes or not PREFIX.fullmatch(paragraph["text"][:link["start"]].strip()):
                continue
            target_url = urljoin(publication_url, link["href"])
            if not consultant_document_id(target_url):
                continue
            if ACTION.search(instruction):
                candidates.extend((scope, target_url, label, paragraph["text"]) for scope in scopes)
    return candidates


def amendment_target_urls(html, publication_url):
    return list(dict.fromkeys(row[1] for row in _target_candidates(html, publication_url)))


def extract_linked_amendments(html, publication_url, document_keys):
    result, seen = [], set()
    digest = hashlib.sha256(html.encode("utf-8")).hexdigest()
    for scope, target_url, label, instruction in _target_candidates(html, publication_url):
        key = document_keys.get(consultant_document_id(target_url))
        if not key:
            continue
        try:
            norm = NormIdentity.from_dict({"document_key": key, "article": scope["article"],
                                           "part": scope["part"] or "", "point": scope["point"] or ""})
        except ValueError:
            continue
        if norm in seen:
            continue
        seen.add(norm)
        result.append(ConfirmedNormChange(norm, {
            "method": "consultant_explicit_link", "publication_url": publication_url,
            "target_url": target_url, "target_label": label,
            "instruction": " ".join(instruction.split())[:2000], "source_sha256": digest,
        }))
    for item in extract_formal_amendments(html, publication_url):
        if item.norm not in seen:
            seen.add(item.norm)
            result.append(item)
    return result


_MONTHS = {name: str(i).zfill(2) for i, name in enumerate(
    ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"), 1)}

def _formal_key(text):
    normalized = re.sub(r"(\d{1,2})\s+("+"|".join(_MONTHS)+r")\s+(\d{4})(?:\s+года)?",
        lambda m: m[1].zfill(2)+"."+_MONTHS[m[2].lower()]+"."+m[3], text, flags=re.I)
    return heading_document_key(normalized)


def _outside_quotes(text, opened=None):
    result = []
    for char in text:
        if opened is None and char in {'"', '«'}:
            opened = '»' if char == '«' else '"'
        elif opened is not None and char == opened:
            opened = None
        elif opened is None:
            result.append(char)
    return "".join(result), opened


def extract_formal_amendments(html, publication_url):
    """Require a dated/numbered law and a formal operation outside inserted text."""
    if not consultant_document_id(publication_url):
        return []
    parser = _Paragraphs()
    parser.feed(html)
    context, opened, result, seen = None, None, [], set()
    digest = hashlib.sha256(html.encode("utf-8")).hexdigest()
    for paragraph in parser.paragraphs:
        raw = " ".join(paragraph["text"].split())
        already_quoted = opened is not None
        text, opened = _outside_quotes(raw, opened)
        if already_quoted:
            continue
        if re.match(r"^Статья\s+\d+(?:\.|$)", text, re.I):
            context = None
        # The instruction header establishes the affected law for following items.
        if re.match(r"^(?:Статья\s+\d+\.\s*)?Внести\s+в\b", text, re.I):
            context = _formal_key(text)
            continue
        action = ACTION.search(text)
        if not action:
            continue
        prefix = re.sub(r"^\d+[).]\s*", "", text[:action.start()].strip())
        scopes = []
        for stop in sorted({len(prefix), *(m.start() for m in re.finditer(r"\s", prefix))}, reverse=True):
            scopes = parse_scope_label(prefix[:stop].strip())
            if scopes:
                break
        if not scopes:
            continue
        tail = prefix[stop:].strip()
        if tail and not (re.match(r"^(?:Федеральн\w*\s+закон\w*|Закон\w*(?:\s+Российской\s+Федерации)?)\s+от\b", tail, re.I)
                or (context and re.fullmatch(r"(?:указанного|данного)\s+закона", tail, re.I))):
            continue
        key = _formal_key(prefix) or context
        if not key:
            continue
        for scope in scopes:
            norm = NormIdentity(key, scope["article"], scope["part"], scope["point"])
            if norm in seen:
                continue
            seen.add(norm)
            result.append(ConfirmedNormChange(norm, {
                "method": "consultant_formal_instruction", "publication_url": publication_url,
                "document_key": key, "instruction": raw[:2000], "source_sha256": digest,
            }))
    return result
