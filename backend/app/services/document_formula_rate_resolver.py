"""Verified rate-data adapter for shared document formula plans.

The formula registry intentionally does not fetch mutable legal data.  This
module is its narrow source boundary: it turns the official Bank of Russia
key-rate history into source-labelled segments for Article 395 of the Civil
Code and Article 236 of the Labour Code.  A failed lookup is reported as a
controlled review state; it is never replaced by a guessed rate or a question
asking a person to research the law.

The registry uses half-open intervals (``start`` is included, ``end`` is
excluded).  The historical CBR helper uses inclusive dates, therefore this
adapter performs the conversion in one audited place.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

from app.services.document_interest_395 import (
    CBR_KEY_RATE_HISTORY_URL,
    KeyRateUnavailable,
    calculate_article_395,
    cbr_key_rate_history,
    rate_periods,
)


def _date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    for layout in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, layout).date()
        except ValueError:
            continue
    return None


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value).replace("\u00a0", "").replace(" ", "").replace(",", "."))
    except InvalidOperation:
        return None
    return parsed if parsed >= 0 else None


def _rule_facts(facts: Mapping[str, Any], rule_id: str) -> dict[str, Any]:
    common = {key: value for key, value in facts.items() if not isinstance(value, Mapping)}
    specific = facts.get(rule_id)
    if isinstance(specific, Mapping):
        common.update(specific)
    return common


def _has_rate_periods(data: Mapping[str, Any]) -> bool:
    return isinstance(data.get("rate_periods") or data.get("segments"), list) and bool(data.get("rate_periods") or data.get("segments"))


def _principal(data: Mapping[str, Any], fields: Mapping[str, Any]) -> Decimal | None:
    candidate = _decimal(data.get("principal", data.get("base_amount")))
    if candidate is not None:
        return candidate
    raw = fields.get("amount", {})
    if isinstance(raw, Mapping) and raw.get("status") in {"filled", "confirmed", "calculated"}:
        return _decimal(raw.get("value"))
    return None


def _payment_events(data: Mapping[str, Any], start: date, end: date, principal: Decimal) -> tuple[list[tuple[date, Decimal]], str | None]:
    """Return literal partial payments grouped by date.

    The product has a precise convention for this deterministic calculation:
    a payment reduces the principal starting on the following calendar day, so
    the payment date itself remains in the preceding delay interval.  The
    convention is rendered in the trace instead of being hidden.  Malformed
    events are never discarded silently.
    """
    raw = data.get("partial_payments")
    if raw is None or raw == "":
        return [], None
    if not isinstance(raw, list):
        return [], "Сведения о частичных платежах не удалось разобрать: укажите дату и сумму каждого платежа отдельно."
    grouped: dict[date, Decimal] = {}
    for item in raw:
        if not isinstance(item, Mapping):
            return [], "Сведения о частичных платежах не удалось разобрать: укажите дату и сумму каждого платежа отдельно."
        paid_on = _date(item.get("date") or item.get("paid_on"))
        amount = _decimal(item.get("amount") or item.get("value"))
        if paid_on is None or amount is None or amount <= 0:
            return [], "Сведения о частичных платежах не удалось разобрать: укажите дату и сумму каждого платежа отдельно."
        if paid_on < start or paid_on >= end:
            return [], "Дата частичного платежа должна относиться к периоду, за который производится расчёт."
        grouped[paid_on] = grouped.get(paid_on, Decimal("0")) + amount
    result = sorted(grouped.items())
    outstanding = principal
    for _, amount in result:
        if amount > outstanding:
            return [], "Сумма частичного платежа превышает остаток долга. Уточните сумму и дату платежа."
        outstanding -= amount
    return result, None


def _payment_intervals(start: date, end: date, principal: Decimal, payments: Iterable[tuple[date, Decimal]]) -> list[tuple[date, date, Decimal]]:
    """Split a half-open delay interval as partial payments reduce the debt."""
    intervals: list[tuple[date, date, Decimal]] = []
    cursor = start
    outstanding = principal
    for paid_on, amount in payments:
        before_reduction_end = min(end, paid_on + timedelta(days=1))
        if cursor < before_reduction_end and outstanding:
            intervals.append((cursor, before_reduction_end, outstanding))
        outstanding -= amount
        cursor = before_reduction_end
    if cursor < end and outstanding:
        intervals.append((cursor, end, outstanding))
    return intervals


def _history_segments(start: date, end: date, principal: Decimal, payments: Iterable[tuple[date, Decimal]], *, labor: bool) -> list[dict[str, str | int]]:
    history = cbr_key_rate_history(end - timedelta(days=1))
    source = CBR_KEY_RATE_HISTORY_URL
    records: list[dict[str, str | int]] = []
    for interval_start, interval_end, outstanding in _payment_intervals(start, end, principal, payments):
        # ``rate_periods`` receives an inclusive last day.
        periods = rate_periods(interval_start, interval_end - timedelta(days=1), history)
        if labor:
            for period in periods:
                records.append({
                    "start": period.start.isoformat(),
                    "end": (period.end + timedelta(days=1)).isoformat(),
                    "days": (period.end - period.start).days + 1,
                    "principal": format(outstanding, "f"),
                    "key_rate_percent": format(period.annual_rate, "f"),
                    "day_divisor": 150,
                    "source": source,
                })
        else:
            segments, _ = calculate_article_395(outstanding, periods)
            for segment in segments:
                records.append({
                    "start": segment.start.isoformat(),
                    "end": (segment.end + timedelta(days=1)).isoformat(),
                    "days": segment.days,
                    "principal": format(outstanding, "f"),
                    "annual_rate": format(segment.annual_rate, "f"),
                    "day_divisor": segment.days_in_year,
                    "source": source,
                })
    return records


def resolve_official_rate_data(
    requested_rule_ids: Iterable[str],
    facts: Mapping[str, Any],
    fields: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Resolve CBR segments for requested rules whose factual period is known.

    Return entries can be merged into formula facts.  Each unavailable source
    is represented as ``source_error`` so the registry can give a meaningful
    system message while keeping the document blocked from export.
    """
    result: dict[str, dict[str, Any]] = {}
    for rule_id in set(requested_rule_ids):
        if rule_id not in {"civil_395", "labor_delay_236"}:
            continue
        data = _rule_facts(facts, rule_id)
        if _has_rate_periods(data):
            continue
        start = _date(data.get("start_date"))
        end = _date(data.get("end_date"))
        principal = _principal(data, fields)
        if start is None or end is None or principal is None or principal <= 0 or end <= start:
            continue
        payments, problem = _payment_events(data, start, end, principal)
        if problem:
            result[rule_id] = {"source_error": problem}
            continue
        try:
            periods = _history_segments(start, end, principal, payments, labor=rule_id == "labor_delay_236")
        except (KeyRateUnavailable, OSError, ValueError, UnicodeError) as error:
            result[rule_id] = {
                "source_error": (
                    "Не удалось автоматически получить проверяемую историю ключевой ставки Банка России. "
                    "Повторите попытку позже; ставку искать или вводить самостоятельно не нужно."
                ),
                "source_error_detail": type(error).__name__,
            }
            continue
        if not periods:
            result[rule_id] = {"source_error": "Официальная история ключевой ставки не покрывает указанный период."}
            continue
        result[rule_id] = {
            "rate_periods": periods,
            "rate_source": CBR_KEY_RATE_HISTORY_URL,
            "partial_payment_convention": "Частичный платёж уменьшает остаток долга со следующего календарного дня.",
        }
    return result
