"""Transparent calculations for statutory default interest under Civil Code art. 395.

The document interview must never ask a person to do the arithmetic or let a
language model guess a historical key rate.  This module contains only
deterministic parsing, rate-history loading and arithmetic.  The workflow
decides which question to show; it can use the ``KeyRateUnavailable`` error to
ask for the one missing factual input rather than silently omit the claim.
"""
from __future__ import annotations

from calendar import isleap
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import lru_cache
from html import unescape
import re
from typing import Any, Callable, Iterable
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener, urlopen


CBR_KEY_RATE_HISTORY_URL = "https://www.cbr.ru/hd_base/KeyRate/"
_KEY_RATE_EPOCH = date(2013, 9, 13)
_ARTICLE_395 = re.compile(
    r"(?:ст(?:атья|\.)?\s*395\b|"
    r"процент\w*.{0,80}?пользован\w*.{0,60}?чуж\w*.{0,60}?(?:денежн\w*|средств\w*)|"
    r"пользован\w*.{0,60}?чуж\w*.{0,60}?(?:денежн\w*|средств\w*))",
    re.IGNORECASE | re.DOTALL,
)
_ARTICLE_395_WITHDRAWN = re.compile(
    r"(?:процент\w*.{0,35}не\s+(?:заявляю|требую)|без\s+процент\w*)",
    re.IGNORECASE,
)
_RATE = re.compile(
    r"(?:ключев\w*\s+ставк\w*|ставк\w*\s+(?:цб|банка\s+россии)|"
    r"ключев\w*)\D{0,25}?(?P<rate>\d{1,2}(?:[.,]\d{1,4})?)\s*%",
    re.IGNORECASE,
)
_NUMERIC_DATE = re.compile(r"\b(?P<day>\d{1,2})[./](?P<month>\d{1,2})[./](?P<year>\d{2,4})\b")
_RU_MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
    "мая": 5, "июня": 6, "июля": 7, "августа": 8,
    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}
_RU_DATE = re.compile(
    r"\b(?P<day>\d{1,2})\s+(?P<month>" + "|".join(_RU_MONTHS) + r")\s+(?P<year>\d{2,4})(?:\s*г(?:ода|\.)?)?\b",
    re.IGNORECASE,
)
_TAG = re.compile(r"<[^>]+>")


class KeyRateUnavailable(RuntimeError):
    """The official history could not cover the requested period."""


@dataclass(frozen=True)
class RatePeriod:
    start: date
    end: date
    annual_rate: Decimal


@dataclass(frozen=True)
class InterestSegment:
    start: date
    end: date
    days: int
    annual_rate: Decimal
    days_in_year: int
    interest: Decimal


KeyRateProvider = Callable[[date, date], Iterable[tuple[date, Decimal] | dict[str, Any]]]


def article_395_requested(state: dict[str, Any], text: str = "") -> bool:
    """Whether the user actually asked for art. 395 interest.

    We inspect only user-originated state, never assistant replies.  A later
    explicit withdrawal wins over an older request, so a person can remove the
    additional claim without being trapped in this branch.
    """
    sources = [str(state.get("request") or ""), text]
    for item in state.get("user_turns", []):
        if isinstance(item, str):
            sources.append(item)
    for key in ("requests", "calculation", "facts"):
        field = state.get("fields", {}).get(key, {})
        if isinstance(field, dict):
            sources.extend(str(field.get(name) or "") for name in ("original", "evidence", "value"))
    current = text or ""
    if _ARTICLE_395_WITHDRAWN.search(current):
        return False
    return any(_ARTICLE_395.search(source) for source in sources if source)


def parse_dates(text: str) -> list[date]:
    """Parse ordinary Russian numeric and written dates without guessing years."""
    result: list[date] = []
    for match in _NUMERIC_DATE.finditer(text or ""):
        try:
            year = int(match["year"])
            if year < 100:
                year += 2000
            result.append(date(year, int(match["month"]), int(match["day"])))
        except ValueError:
            continue
    for match in _RU_DATE.finditer(text or ""):
        try:
            year = int(match["year"])
            if year < 100:
                year += 2000
            result.append(date(year, _RU_MONTHS[match["month"].lower()], int(match["day"])))
        except ValueError:
            continue
    return list(dict.fromkeys(result))


def field_dates(state: dict[str, Any], key: str) -> list[date]:
    field = state.get("fields", {}).get(key, {})
    if not isinstance(field, dict):
        return []
    values = [field.get(name) for name in ("value", "original", "evidence")]
    dates: list[date] = []
    for value in values:
        if not value:
            continue
        if isinstance(value, str):
            try:
                dates.append(datetime.strptime(value, "%Y-%m-%d").date())
                continue
            except ValueError:
                pass
        dates.extend(parse_dates(str(value)))
    return list(dict.fromkeys(dates))


def due_date_start(state: dict[str, Any]) -> date | None:
    """The first day of delay is the day following an explicitly stored due date."""
    dates = field_dates(state, "due_date")
    return dates[0] + timedelta(days=1) if dates else None


def explicit_rate(text: str) -> Decimal | None:
    match = _RATE.search(text or "")
    if not match:
        return None
    try:
        rate = Decimal(match["rate"].replace(",", "."))
    except InvalidOperation:
        return None
    return rate if Decimal("0") < rate <= Decimal("100") else None


def no_partial_payments(state: dict[str, Any]) -> bool | None:
    """Return False for known repayments, True for an express absence, None otherwise."""
    field = state.get("fields", {}).get("payments", {})
    if not isinstance(field, dict) or field.get("status") not in {"filled", "unknown", "not_applicable"}:
        return None
    text = " ".join(str(field.get(name) or "") for name in ("value", "original", "evidence"))
    if re.search(r"\b(?:нет|не было|отсутств|не получал|не возвращал|никак(?:их|ого)\s+платеж)", text, re.I):
        return True
    if field.get("status") in {"unknown", "not_applicable"}:
        return None
    return False if text.strip() else None


def _rate_decimal(raw: Any) -> Decimal | None:
    try:
        value = Decimal(str(raw).replace(" ", "").replace(",", "."))
    except InvalidOperation:
        return None
    return value if Decimal("0") < value <= Decimal("100") else None


def _date_from_value(raw: Any) -> date | None:
    if isinstance(raw, date):
        return raw
    parsed = parse_dates(str(raw or ""))
    return parsed[0] if parsed else None


def normalize_rate_history(rows: Iterable[tuple[date, Decimal] | dict[str, Any]]) -> list[tuple[date, Decimal]]:
    """Validate provider rows and retain only actual changes of the key rate.

    The current CBR page can emit a daily observation even when the rate did
    not change.  Treating each observation as a new period rounds the same
    monthly interest dozens of times and produces a noisy, legally misleading
    calculation.  A rate stays effective until the next different verified
    rate, so equal consecutive rows are deliberately collapsed here.
    """
    normalized: list[tuple[date, Decimal]] = []
    for row in rows:
        if isinstance(row, dict):
            effective = _date_from_value(row.get("effective_from") or row.get("date") or row.get("start"))
            rate = _rate_decimal(row.get("annual_rate") or row.get("rate"))
        elif isinstance(row, tuple) and len(row) == 2:
            effective, rate = _date_from_value(row[0]), _rate_decimal(row[1])
        else:
            continue
        if effective is not None and rate is not None:
            normalized.append((effective, rate))
    unique = sorted(dict(normalized).items(), key=lambda item: item[0])
    changes: list[tuple[date, Decimal]] = []
    for effective, rate in unique:
        if changes and changes[-1][1] == rate:
            continue
        changes.append((effective, rate))
    return changes


def parse_cbr_key_rate_history(html: str) -> list[tuple[date, Decimal]]:
    """Extract dated rate rows from the fixed official CBR history page.

    The public page is HTML rather than a stable JSON API.  Parsing is kept
    deliberately narrow: a row must contain an unambiguous date followed by a
    plausible percentage.  Any layout change produces an empty result and the
    caller treats it as unavailable, never as a zero/default rate.
    """
    rows: list[tuple[date, Decimal]] = []
    for raw_row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", html or "", re.IGNORECASE | re.DOTALL):
        plain = re.sub(r"\s+", " ", _TAG.sub(" ", unescape(raw_row))).strip()
        date_match = _NUMERIC_DATE.search(plain)
        if not date_match:
            continue
        date_value = _date_from_value(date_match[0])
        if date_value is None:
            continue
        tail = plain[date_match.end():]
        rate_match = re.search(r"(?<!\d)(\d{1,2}(?:[.,]\d{1,4})?)(?!\d)", tail)
        rate = _rate_decimal(rate_match[1]) if rate_match else None
        if rate is not None:
            rows.append((date_value, rate))
    return normalize_rate_history(rows)


def _cbr_history_url(end: date) -> str:
    # The history needs a rate that was already effective on the first day of
    # the requested interval.  The key rate started in 2013; requesting the
    # entire public history avoids silently substituting a later rate.
    query = urlencode({
        "UniDbQuery.Posted": "True",
        "UniDbQuery.From": _KEY_RATE_EPOCH.strftime("%d.%m.%Y"),
        "UniDbQuery.To": end.strftime("%d.%m.%Y"),
    })
    return CBR_KEY_RATE_HISTORY_URL + "?" + query


def _cbr_proxy_url() -> str:
    """Return the optional fixed local route for the official CBR source.

    Docker Desktop on this host intermittently cannot complete a TLS handshake
    with cbr.ru, while the Windows host can.  The configured route is a local
    allow-listed CONNECT tunnel, not a general-purpose outbound proxy.
    """
    from app.core.config import get_settings

    return str(get_settings().CBR_PROXY_URL or "").strip()


def _fetch_cbr_page(url: str) -> str:
    request = Request(url, headers={"User-Agent": "Legal-AI-service/1.0", "Accept": "text/html"})
    proxy_url = _cbr_proxy_url()
    opener = build_opener(ProxyHandler({"https": proxy_url})) if proxy_url else None
    open_page = opener.open if opener is not None else urlopen
    with open_page(request, timeout=15) as response:  # noqa: S310 -- fixed official HTTPS endpoint
        if getattr(response, "status", 200) != 200:
            raise KeyRateUnavailable("CBR returned a non-success status")
        return response.read(1_500_000).decode("utf-8", errors="replace")


@lru_cache(maxsize=32)
def cbr_key_rate_history(end: date) -> tuple[tuple[date, Decimal], ...]:
    """Load official history once per calculation end date.

    Network or parsing errors become a controlled calculation state.  The
    system never falls back to a stale guessed rate.
    """
    try:
        history = parse_cbr_key_rate_history(_fetch_cbr_page(_cbr_history_url(end)))
    except (OSError, ValueError, UnicodeError, KeyRateUnavailable) as error:
        raise KeyRateUnavailable("Official key-rate history is unavailable") from error
    if not history:
        raise KeyRateUnavailable("Official key-rate history is empty")
    return tuple(history)


def rate_periods(start: date, end: date, history: Iterable[tuple[date, Decimal] | dict[str, Any]]) -> list[RatePeriod]:
    if end < start:
        raise ValueError("The end date precedes the first day of delay")
    rows = normalize_rate_history(history)
    applicable = [(effective, rate) for effective, rate in rows if effective <= end]
    before_start = [(effective, rate) for effective, rate in applicable if effective <= start]
    if not before_start:
        raise KeyRateUnavailable("Rate history does not cover the first day of delay")
    result: list[RatePeriod] = []
    for index, (effective, rate) in enumerate(applicable):
        next_effective = applicable[index + 1][0] if index + 1 < len(applicable) else end + timedelta(days=1)
        period_start = max(start, effective)
        period_end = min(end, next_effective - timedelta(days=1))
        if period_start <= period_end:
            result.append(RatePeriod(period_start, period_end, rate))
    if not result:
        raise KeyRateUnavailable("Rate history produced no covered days")
    return result


def calculate_article_395(principal: Decimal, periods: Iterable[RatePeriod]) -> tuple[list[InterestSegment], Decimal]:
    """Calculate per rate period and calendar year with traceable rounding."""
    if principal <= 0:
        raise ValueError("Principal must be positive")
    segments: list[InterestSegment] = []
    for period in periods:
        cursor = period.start
        while cursor <= period.end:
            year_end = date(cursor.year, 12, 31)
            segment_end = min(period.end, year_end)
            days = (segment_end - cursor).days + 1
            denominator = 366 if isleap(cursor.year) else 365
            interest = (principal * period.annual_rate / Decimal("100") * Decimal(days) / Decimal(denominator)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            segments.append(InterestSegment(cursor, segment_end, days, period.annual_rate, denominator, interest))
            cursor = segment_end + timedelta(days=1)
    total = sum((item.interest for item in segments), Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return segments, total


def format_money(value: Decimal | str) -> str:
    amount = Decimal(value)
    return format(amount, ",.2f").replace(",", " ") + " рублей"


def format_rate(value: Decimal) -> str:
    return format(value.normalize(), "f").replace(".", ",") + " %"


def interest_formula(principal: Decimal, segments: Iterable[InterestSegment]) -> str:
    parts = []
    for item in segments:
        period = f"с {item.start:%d.%m.%Y} по {item.end:%d.%m.%Y}"
        parts.append(
            f"{period}: {format_money(principal)} × {format_rate(item.annual_rate)} × "
            f"{item.days} дн. / {item.days_in_year} = {format_money(item.interest)}"
        )
    total = sum((item.interest for item in segments), Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return "Проценты за пользование чужими денежными средствами по статье 395 ГК РФ: " + "; ".join(parts) + f". Всего процентов: {format_money(total)}."

