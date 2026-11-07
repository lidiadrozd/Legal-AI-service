"""Deterministic typography: never ask the model to group monetary digits."""
from decimal import Decimal
import re


def format_money(value):
    amount=Decimal(str(value).replace('\u00a0','').replace(' ','').replace(',','.'))
    integral=amount==amount.to_integral_value()
    number=format(amount,',.0f' if integral else ',.2f').replace(',',' ').replace('.',',')
    return number


def normalize_monetary_text(text):
    pattern=r'(?<![\w\d./№+-])(\d+(?:[ \u00a0]\d{3})*(?:[.,]\d{1,2})?)\s*(руб(?:лей|ля|ль|\.)?|₽)(?![а-яё])'
    return re.sub(pattern,lambda m:format_money(m[1])+' '+m[2],text,flags=re.I)


def normalize_prose_dates(text):
    """Print unambiguous ISO dates consistently, preserving numbered identifiers."""
    from datetime import date
    def convert(match):
        if re.search(r'(?:№|номер)\s*$',text[max(0,match.start()-15):match.start()],re.I):return match[0]
        try:return date.fromisoformat(match[0]).strftime('%d.%m.%Y')
        except ValueError:return match[0]
    return re.sub(r'(?<![\w/№-])(?:19|20)\d{2}-\d{2}-\d{2}(?![\w/-])',convert,text)


# Provenance belongs to the field metadata (``sources`` / ``source_urls``),
# not to the body of a filing.  Older calculation plans could nevertheless
# put a catalogue URL and a database-revision note into a legal ground.  Keep
# the substantive citation, but never print those implementation details in a
# formal document.  The URL pattern also accepts a value that was escaped
# during JSON/OOXML handling, for example ``https\\://www\\.consultant.ru``.
_SOURCE_URL = re.compile(
    r"(?i)\bhttps?(?:\\+)?:(?:\\+)?//(?:\\.|[^\s<>()\[\]{}\"'])*"
)
_CATALOGUE_REVISION = re.compile(
    r"\s*\(\s*(?:редакц(?:ия|ии)|версия|актуальная\s+редакция)\b[^)]*\)",
    re.I,
)


def clean_legal_citation_text(text):
    """Remove source-system artefacts while retaining a legal citation.

    This is deliberately a presentation boundary rather than a fact editor:
    it applies only to the generated state-duty field in
    ``format_template_fields``.  A party may still provide a web address as
    evidence in an ordinary factual field, while the fee ground remains proper
    prose even for legacy saved chats.
    """
    if not isinstance(text, str):
        return text
    cleaned = _SOURCE_URL.sub("", text)
    cleaned = _CATALOGUE_REVISION.sub("", cleaned)
    # Older tariff records began with the code name.  In a formal document a
    # pinpoint citation reads naturally in the opposite order; normalise this
    # legacy form without altering the article or paragraph numbers.
    cleaned = re.sub(
        r"(?i)\bНК\s+РФ\s*,\s*"
        r"(подпункт\s+\d+\s+пункта\s+\d+\s+статьи\s+\d+(?:\.\d+)?)",
        r"\1 НК РФ",
        cleaned,
    )
    # Remove a source label left behind by a deleted URL, then repair only the
    # whitespace/punctuation junctions that the deletion created.
    cleaned = re.sub(r"(?i)(?:\s*[;,]\s*)?(?:ссылка|источник|url)\s*:\s*(?=[;,.\s]*$)", "", cleaned)
    cleaned = re.sub(r"\s*;\s*([.,])", r"\1", cleaned)
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    cleaned = re.sub(r"(?:;\s*)+$", "", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()
