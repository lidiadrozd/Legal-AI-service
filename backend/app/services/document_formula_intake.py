"""Source-bound intake adapter for the shared monetary formula registry.

The registry deliberately knows no conversational Russian and no template
cursor.  This module supplies that boundary: it records only literal factual
inputs from a user turn, invokes the deterministic registry, and leaves a
single precise follow-up on the actual form field.  It is shared by claims,
pretensions, motions and future templates.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import json
import re
from typing import Any, Mapping

from app.services.document_formula_registry import (
    CALCULATED,
    NEEDS_INPUT,
    REVIEW_REQUIRED,
    apply_plan_to_state,
    build_calculation_plan,
    detect_requested_rules,
    managed_formula_facts,
)


_MONTHS = {
    "января": 1, "январь": 1, "февраля": 2, "февраль": 2,
    "марта": 3, "март": 3, "апреля": 4, "апрель": 4,
    "мая": 5, "май": 5, "июня": 6, "июнь": 6,
    "июля": 7, "июль": 7, "августа": 8, "август": 8,
    "сентября": 9, "сентябрь": 9, "октября": 10, "октябрь": 10,
    "ноября": 11, "ноябрь": 11, "декабря": 12, "декабрь": 12,
}
_DATE = re.compile(
    r"(?<!\d)(\d{1,2})[./](\d{1,2})[./](\d{2,4})(?!\d)|"
    r"(?<!\d)(\d{1,2})\s+(" + "|".join(_MONTHS) + r")\s+(\d{4})(?:\s*г(?:ода|\.)?)?",
    re.I,
)
_MONEY = re.compile(
    r"(?<![\w\d/№])(\d{1,3}(?:[ \u00a0]\d{3})+|\d+)(?:[,.](\d{1,2}))?\s*"
    r"(?:руб(?:лей|ля|ль|\.)?|₽)",
    re.I,
)
_RATE = re.compile(
    r"(\d+(?:[,.]\d{1,4})?)\s*%\s*(?:"
    r"(?:за\s+(?:кажд\w+\s*)?|в\s*)?(день|дня|дней|сутки|год|года|лет|месяц|месяца|месяцев))",
    re.I,
)
_DAYS = re.compile(r"\b(\d{1,5})\s*(?:календарн\w*\s*)?(?:дн(?:я|ей)?|сут\w*)", re.I)
_NO_PAYMENTS = re.compile(
    r"\b(?:не\s+(?:платил\w*|возвращал\w*|оплачивал\w*|получал\w*)|"
    r"платеж(?:ей|и)?\s+не\s+(?:было|поступал\w*)|частичн\w*\s+платеж(?:ей|и)?\s+не\s+было|"
    r"ничего\s+не\s+(?:вернул\w*|возвращено|оплатил\w*))\b",
    re.I,
)
_PAYMENT_CONTEXT = re.compile(
    r"\b(?:частичн\w*\s+плат[её]ж\w*|"
    r"(?:внес|внесла|внёс|оплатил\w*|погасил\w*|вернул\w*|перев[её]л\w*|"
    r"перечисл\w*|заплатил\w*|уплатил\w*)"
    r")\b",
    re.I,
)
_DIRECT_CALCULATION = re.compile(r"\b(?:рассчита\w*|посчита\w*|подсчита\w*|слож\w*)\b", re.I)
_FORMULA_REPLY_FIELDS = {
    "calculation", "penalty_calculation", "period_payments", "costs", "litigation_costs",
    # Some pretense forms have no separate calculation control: the precise
    # formula follow-up is therefore asked in the claim/requests slot.
    "additional_claims", "requests",
}

_STATIC_CONSUMER_RULES = {
    # The cap is a property of the chosen legal regime, not an assumption
    # about every consumer demand.  The Article 23 remedy for a defective
    # good, for example, is not silently capped by its purchase price here.
    "claim_consumer_late_delivery": {"rate": "0.5", "source": "Статья 23.1 Закона РФ «О защите прав потребителей»", "cap": True},
    "pretense_consumer_late_delivery": {"rate": "0.5", "source": "Статья 23.1 Закона РФ «О защите прав потребителей»", "cap": True},
    "claim_consumer_defective_goods": {"rate": "1", "source": "Статья 23 Закона РФ «О защите прав потребителей»", "cap": False},
    "pretense_consumer_defective_goods": {"rate": "1", "source": "Статья 23 Закона РФ «О защите прав потребителей»", "cap": False},
    "pretense_consumer_defective_service": {"rate": "3", "source": "Статьи 28 и 31 Закона РФ «О защите прав потребителей»", "cap": True},
}
_ALIMONY_PENALTY_SOURCE = "Статья 115 Семейного кодекса Российской Федерации"
_CONSUMER_BUSINESS_PURPOSE = re.compile(r"перепродаж|предпринимател|коммерческ|бизнес|профессиональ", re.I)
_CONSUMER_PERSONAL_PURPOSE = re.compile(r"личн|семейн|домашн|для\s+себя|собственн\w*\s+потреблен", re.I)


def _field_value(state: Mapping[str, Any], key: str) -> str | None:
    item = (state.get("fields") or {}).get(key, {})
    if isinstance(item, Mapping) and item.get("status") == "filled" and item.get("value") not in {None, ""}:
        return str(item["value"])
    return None


def _as_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    for layout in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, layout).date()
        except ValueError:
            pass
    return None


def _dates(text: str) -> list[date]:
    return [parsed for parsed, _, _ in _date_matches(text)]


def _date_matches(text: str) -> list[tuple[date, int, int]]:
    """Return literal dates with offsets, without interpreting their role.

    Offsets let the payment parser distinguish dates of partial payments from
    the end date of a calculation.  That is important for a natural answer
    such as ``"расчёт по 01.09; 20.07 возвращено 20 000"``: the payment date
    must not become the start of the delay period.
    """
    values: list[tuple[date, int, int]] = []
    for match in _DATE.finditer(text or ""):
        try:
            if match[1]:
                year = int(match[3])
                if year < 100:
                    year += 2000 if year <= 68 else 1900
                parsed = date(year, int(match[2]), int(match[1]))
            else:
                parsed = date(int(match[6]), _MONTHS[match[5].casefold()], int(match[4]))
        except (KeyError, ValueError):
            continue
        if all(existing != parsed for existing, _, _ in values):
            values.append((parsed, match.start(), match.end()))
    return values


def _money_values(text: str) -> list[str]:
    values: list[str] = []
    for rendered, _, _ in _money_matches(text):
        if rendered not in values:
            values.append(rendered)
    return values


def _money_matches(text: str) -> list[tuple[str, int, int]]:
    """Return positive rouble sums and their literal positions."""
    values: list[tuple[str, int, int]] = []
    for match in _MONEY.finditer(text or ""):
        raw = match[1].replace("\u00a0", "").replace(" ", "")
        if match[2]:
            raw += "." + match[2]
        try:
            value = Decimal(raw)
        except InvalidOperation:
            continue
        if value > 0:
            rendered = format(value.quantize(Decimal("0.01")), "f")
            # Keep repeated literal sums.  Two instalments or two partial
            # payments can legitimately have the same amount.
            values.append((rendered, match.start(), match.end()))
    return values


def _clause_ranges(text: str) -> list[tuple[int, int]]:
    """Return short factual clauses, preserving their offsets in ``text``."""
    # A full stop is part of Russian numeric dates, but a full stop followed
    # by whitespace and a new date/upper-case sentence does delimit a factual
    # row.  This keeps ``01.09.2026`` intact while handling prose rather than
    # requiring a semicolon-separated list.
    source = text or ""
    result: list[tuple[int, int]] = []
    cursor = 0
    for separator in re.finditer(r"[;\n]+|\.(?=\s+(?:[А-ЯЁ]|\d{1,2}[./]))", source):
        if cursor < separator.start():
            result.append((cursor, separator.start()))
        cursor = separator.end()
    if cursor < len(source):
        result.append((cursor, len(source)))
    return result


def _payment_clause_ranges(text: str) -> list[tuple[int, int]]:
    source = text or ""
    ranges: list[tuple[int, int]] = []
    list_mode = False
    for start, end in _clause_ranges(source):
        clause = source[start:end]
        header = re.search(r"\bчастичн\w*\s+плат[её]ж\w*\b", clause, re.I)
        # A heading such as "Частичные платежи: ..." authorises the listed
        # rows that follow it.  A standalone payment verb authorises just its
        # own clause.  This supports both a table-like list and normal prose.
        if header:
            list_mode = True
            # Text before the heading may include the requested date of
            # calculation; it is not a payment row.
            ranges.append((start + header.start(), end))
        elif _PAYMENT_CONTEXT.search(clause) or list_mode:
            ranges.append((start, end))
    return ranges


def _payment_events_from_text(text: str) -> list[dict[str, str]]:
    """Parse literal dated repayments from ordinary Russian prose.

    We deliberately require a payment verb (``вернул``, ``погасил``,
    ``частичный платёж`` and similar) in the same short clause.  A date and a
    rouble amount without that context can be the original loan and must not
    reduce its principal by accident.  Each event stays literal; validation
    of its place in the calculation period is done by the source-bound rate
    resolver.
    """
    events: list[dict[str, str]] = []
    for start, end in _payment_clause_ranges(text):
        clause = (text or "")[start:end]
        dates = _date_matches(clause)
        amounts = _money_matches(clause)
        if not dates or not amounts:
            continue
        # Natural answers usually give one date and one amount per clause.
        # When there are several, preserve their left-to-right pairing rather
        # than making a monetary assumption about unmatched fragments.
        if len(dates) == 1:
            pairs = [(dates[0][0], amount[0]) for amount in amounts]
        elif len(dates) == len(amounts):
            pairs = [(dates[index][0], amounts[index][0]) for index in range(len(dates))]
        else:
            # Do not guess which of several dates belongs to a single sum.
            continue
        for paid_on, amount in pairs:
            event = {"date": paid_on.isoformat(), "amount": amount}
            if event not in events:
                events.append(event)
    return events


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(base))
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _rule_ids(state: Mapping[str, Any], text: str) -> set[str]:
    scenario = str(state.get("scenario") or "")
    ids = detect_requested_rules(scenario, text)
    ids.update(
        str(item) for item in state.get("formula_requested_rules", ())
        if isinstance(item, str)
    )
    plan = state.get("calculation_plan")
    if isinstance(plan, Mapping) and not plan.get("deferred"):
        ids.update(str(item) for item in plan.get("unresolved_rule_ids") or () if item)
    return ids


def _source_dates(state: Mapping[str, Any], *, consumer: bool = False) -> tuple[date | None, date | None]:
    start_keys = ("delivery_due", "due_date", "payment_due", "wages_due") if consumer else ("due_date", "payment_due", "wages_due", "delivery_due")
    end_keys = ("delivery_date", "delivery_status", "payment_date", "date") if consumer else ("payment_date", "date", "delivery_status")
    def from_field(key: str) -> date | None:
        value = _field_value(state, key)
        return _as_date(value) or next(iter(_dates(value or "")), None)
    start = next((from_field(key) for key in start_keys if from_field(key)), None)
    end = next((from_field(key) for key in end_keys if from_field(key)), None)
    return start, end


def _set_dates(
    data: dict[str, Any],
    state: Mapping[str, Any],
    text: str,
    current: str | None,
    *,
    consumer: bool = False,
    ignored_dates: set[date] | None = None,
) -> None:
    # An explicit calculation interval wins over unrelated dates of transfer,
    # contract and demand. "с 1 по 30 октября" shares month and year.
    endpoint = re.fullmatch(r'\s*(?:(?:до|по)\s+)?(?P<date>' + _DATE.pattern + r')\s*(?:включительно)?[.!]?\s*', text, re.I)
    if (current in _FORMULA_REPLY_FIELDS and endpoint and data.get('start_date')
            and not data.get('end_date') and re.search(r'\d{4}', text)):
        candidates = _dates(endpoint['date'])
        if len(candidates) == 1 and len(text.strip()) < 65:
            left, right = _as_date(data['start_date']), candidates[0]
            if left and right >= left:
                data.update(end_date=right.isoformat(), days=(right-left).days + 1, explicit_interval=True)
                return
    interval=re.search(r'\bс\s+(\d{1,2})\s+по\s+(\d{1,2})\s+('+'|'.join(_MONTHS)+r')\s+(\d{4})(?:\s+года)?\s*(включительно)?',text,re.I)
    if interval:
        try:
            left=date(int(interval[4]),_MONTHS[interval[3].lower()],int(interval[1]))
            right=date(int(interval[4]),_MONTHS[interval[3].lower()],int(interval[2]))
        except ValueError:return
        if right>=left:
            data.update(start_date=left.isoformat(),end_date=right.isoformat(),days=(right-left).days+(1 if interval[5] else 0),explicit_interval=True)
        return
    if data.get('explicit_interval') and not re.search(r'период|расч[её]т\s+(?:с|по)|считать\s+(?:с|по)',text,re.I):
        return
    found = [item for item in _dates(text) if item not in (ignored_dates or set())]
    start, end = _source_dates(state, consumer=consumer)
    if current in {"due_date", "delivery_due", "payment_due", "wages_due"} and found:
        start = found[0]
    elif current in {"payment_date", "delivery_status", "delivery_date"} and found:
        end = found[-1]
    elif len(found) >= 2:
        start, end = found[0], found[-1]
    elif len(found) == 1:
        # In a dedicated formula follow-up a single date completes the missing
        # endpoint.  We never reinterpret it as both dates.
        if not start:
            start = found[0]
        elif not end:
            end = found[0]
    if start:
        # The first day of an ordinary payment delay follows the agreed due
        # date.  When the user explicitly gives a date in a formula answer we
        # retain it verbatim as the start date instead.
        # A lone date in a calculation answer is normally the requested end
        # date while the due date is already stored in the form.  Treat a
        # start date as explicit only when the user actually supplied both
        # endpoints in this answer.
        explicit_start = len(found) >= 2
        data["start_date"] = (start if explicit_start else start + timedelta(days=1)).isoformat()
    if end:
        data["end_date"] = end.isoformat()
    if data.get("start_date") and data.get("end_date"):
        left = _as_date(data["start_date"])
        right = _as_date(data["end_date"])
        if left and right and right > left:
            data["days"] = (right - left).days


def _set_contract_rate(data: dict[str, Any], text: str) -> None:
    match = _RATE.search(text or "")
    if not match:
        match=re.search(r'(\d+(?:[,.]\d{1,4})?)\s*%[^.!?;]{0,100}?за\s+(?:каждый\s+)?(?:календарный\s+)?(день|год|месяц)\b',text,re.I)
    if match:
        period = match[2].casefold()
        data["rate_percent"] = match[1].replace(",", ".")
        data["rate_period"] = "day" if period.startswith(("ден", "сут")) else "year" if period.startswith("год") else "month"
        data["contract_clause"] = text.strip()
    days = _DAYS.search(text or "")
    if days:
        data["days"] = days[1]


def _set_installments(data: dict[str, Any], text: str) -> None:
    """Record every fully specified overdue alimony instalment in a turn.

    A person can write several ordinary clauses at once, for example:
    ``за июль — 10 000 рублей, просрочка 30 дней; за август — 8 000
    рублей, просрочка 10 дней``.  The old code silently retained only the
    first pair.  We only accept clauses where amount and number of overdue
    days can be paired one-to-one, so an incomplete fragment remains a
    question instead of becoming a fictitious calculation.
    """
    found: list[dict[str, str]] = []
    for start, end in _clause_ranges(text):
        clause = (text or "")[start:end]
        amounts = _money_matches(clause)
        days = list(_DAYS.finditer(clause))
        if not amounts or not days or len(amounts) != len(days):
            continue
        for amount, overdue in zip(amounts, days):
            installment = {
                "debt": amount[0],
                "days": overdue[1],
                "daily_rate_percent": "0.1",
                "rate_source": _ALIMONY_PENALTY_SOURCE,
            }
            if installment not in found:
                found.append(installment)
    if found:
        existing = data.get("installments")
        merged = list(existing) if isinstance(existing, list) else []
        for installment in found:
            if installment not in merged:
                merged.append(installment)
        data["installments"] = merged


def _consumer_policy(state: Mapping[str, Any]) -> dict[str, Any]:
    scenario = str(state.get("scenario") or "")
    purpose = " ".join(filter(None, (
        _field_value(state, "consumer_status"), _field_value(state, "procedure"),
        _field_value(state, "purpose"), _field_value(state, "acquisition_purpose"),
    )))
    if _CONSUMER_BUSINESS_PURPOSE.search(purpose):
        return {
            "consumer_policy_error": (
                "По указанной предпринимательской или перепродажной цели покупки специальная "
                "потребительская неустойка не применяется автоматически."
            ),
        }
    chosen = _STATIC_CONSUMER_RULES.get(scenario)
    if not chosen and scenario == "claim_consumer":
        # The universal form may describe a consumer or a commercial dispute.
        # Its statutory rate is selected only after the person confirms the
        # factual personal/household purpose, never merely because the form
        # title contains the word "consumer".
        if not _CONSUMER_PERSONAL_PURPOSE.search(purpose):
            return {
                "consumer_policy_missing_field": "procedure",
                "consumer_policy_question": (
                    "Уточните фактическую цель покупки: для личных, семейных или домашних нужд "
                    "либо для предпринимательской деятельности."
                ),
            }
        category = " ".join(filter(None, (
            _field_value(state, "category"), _field_value(state, "purchase"), _field_value(state, "defects"),
            _field_value(state, "facts"), _field_value(state, "seller_response"), _field_value(state, "requests"),
        ))).casefold()
        if re.search(r"достав|передач|предоплат", category):
            chosen = {"rate": "0.5", "source": "Статья 23.1 Закона РФ «О защите прав потребителей»", "cap": True}
        elif re.search(r"услуг|работ|ремонт|подряд", category):
            chosen = {"rate": "3", "source": "Статьи 28 и 31 Закона РФ «О защите прав потребителей»", "cap": True}
        elif re.search(r"товар|покуп", category):
            chosen = {"rate": "1", "source": "Статья 23 Закона РФ «О защите прав потребителей»", "cap": False}
    if not chosen:
        return {
            "consumer_policy_missing_field": "category",
            "consumer_policy_question": (
                "Уточните, что приобреталось или заказывалось и в чём состоит нарушение: "
                "просрочка передачи товара, недостаток товара либо недостаток работы или услуги."
            ),
        }
    rate, source = chosen["rate"], chosen["source"]
    amount = _field_value(state, "amount")
    data: dict[str, Any] = {"daily_rate_percent": rate, "rate_source": source}
    if amount:
        data["principal"] = amount
        if chosen["cap"]:
            data["cap_amount"] = amount
    return data


def _contract_payment_balance(state, data, text):
    """Keep the opening calculation base separate from the remaining debt."""
    from decimal import Decimal
    opening=re.search(r'(?:оставшиеся|остаток\s+(?:долга|задолженности)(?:\s+составлял)?)\s+('+_MONEY.pattern+r')',text,re.I)
    if opening:
        amount=_money_matches(opening[0])
        if amount:data.update(principal=amount[0][0],opening_evidence=opening[0])
    if re.search(r'(?:со\s+дня|в\s+день)\s+(?:поступления|оплаты|платежа)',text,re.I):
        data['payment_day_policy']='same_day'
    elif re.search(r'со\s+следующего\s+дня',text,re.I):
        data['payment_day_policy']='next_day'
    payments=data.get('partial_payments') or []
    start=_as_date(data.get('start_date'))
    if not payments or not start:return
    payments=[p for p in payments if _as_date(p.get('date')) and _as_date(p['date'])>=start]
    data['partial_payments']=payments
    if not payments:return
    if not data.get('opening_evidence'):
        # The amount field may be today's balance, not the opening balance.
        # Never charge the whole period on it without a dated starting base.
        data['principal']=None
        return
    remaining=Decimal(data['principal'])-sum((Decimal(p['amount']) for p in payments),Decimal('0'))
    if remaining<0:return
    evidence=data['opening_evidence']+'; '+'; '.join(p.get('evidence','') for p in payments)
    state['fields']['amount']={'status':'filled','value':format(remaining,'.2f'),
        'evidence':evidence,'origin':'source_bound_arithmetic','inputs':{'opening':data['principal'],'payments':payments}}


def _capture_rule_facts(state: dict[str, Any], text: str, current: str | None, rule_ids: set[str]) -> None:
    facts = state.setdefault("calculation_facts", {})
    if not isinstance(facts, dict):
        facts = state["calculation_facts"] = {}
    for rule_id in rule_ids:
        if rule_id not in {
            "civil_395", "contract_interest", "contract_penalty", "consumer_delay_penalty",
            "labor_delay_236", "alimony_penalty", "interest_basis", "penalty_basis", "court_costs",
        }:
            continue
        rule_facts = facts.setdefault(rule_id, {})
        if not isinstance(rule_facts, dict):
            rule_facts = facts[rule_id] = {}
        rule_facts.setdefault("evidence", []).append(text)
        if rule_id in {"civil_395", "labor_delay_236", "contract_interest", "contract_penalty"}:
            loan = state.get('loan_facts', {}) if rule_id in {'contract_interest', 'contract_penalty'} else {}
            if loan.get('principal'):
                rule_facts['principal'] = loan['principal']
                if loan.get('payments'):
                    rule_facts['partial_payments'] = deepcopy(loan['payments'])
                if re.search(r'(?:со\s+дня|в\s+день)\s+(?:поступления|оплаты|платежа)', text, re.I):
                    rule_facts['payment_day_policy'] = 'same_day'
                elif re.search(r'со\s+следующего\s+дня', text, re.I):
                    rule_facts['payment_day_policy'] = 'next_day'
            if _NO_PAYMENTS.search(re.sub(r'Других\s+платежей\s+не\s+было','',text,flags=re.I)):
                rule_facts["partial_payments"] = []
                payment_dates: set[date] = set()
            else:
                payments = _payment_events_from_text(text)
                payment_dates = {parsed for item in payments if (parsed := _as_date(item.get("date")))}
                if payments and not loan.get('principal'):
                    existing = rule_facts.get("partial_payments")
                    merged = list(existing) if isinstance(existing, list) else []
                    for payment in payments:
                        if payment not in merged:
                            merged.append(payment)
                    rule_facts["partial_payments"] = merged
            formula_date_reply = current in _FORMULA_REPLY_FIELDS and len(text.strip()) < 65 and bool(_dates(text))
            if loan.get('principal') and not formula_date_reply and not re.search(r'\bс\s+\d.{0,45}\bпо\s+\d|период|первый день', text, re.I):
                _set_dates(rule_facts, state, '', current, ignored_dates=payment_dates)
            else:
                _set_dates(rule_facts, state, text, current, ignored_dates=payment_dates)
            if rule_id in {"contract_interest", "contract_penalty"}:
                _set_contract_rate(rule_facts, text)
                if not loan.get('principal'):
                    _contract_payment_balance(state, rule_facts, text)
        elif rule_id == "consumer_delay_penalty":
            rule_facts.update(_consumer_policy(state))
            _set_dates(rule_facts, state, text, current, consumer=True)
        elif rule_id == "alimony_penalty":
            _set_installments(rule_facts, text)
        elif rule_id in {"interest_basis", "penalty_basis"}:
            # The user's next literal answer (for example, "по статье 395")
            # is retained as evidence. Detection on the next planning pass
            # turns it into the concrete rule without making up a basis.
            rule_facts["answer"] = text.strip()


def _plan_facts(state: Mapping[str, Any]) -> dict[str, Any]:
    managed = managed_formula_facts(state)
    user_facts = state.get("calculation_facts")
    return _deep_merge(managed, user_facts if isinstance(user_facts, Mapping) else {})


def should_plan(state: Mapping[str, Any], text: str = "", current: str | None = None) -> bool:
    if not state.get("scenario"):
        return False
    if _rule_ids(state, text):
        return True
    if state.get("calculation_facts") or state.get("calculation_plan"):
        return True
    if state.get("scenario") == "claim_alimony_fixed" and (current == "monthly_amount" or _field_value(state, "monthly_amount")):
        return True
    # A completed source-bound arithmetic ledger is the factual point at
    # which a standard civil property duty can be calculated.  Do not start
    # this branch from a lone amount earlier in the questionnaire.
    from app.services.document_state_duty_policy import is_ordinary_civil_property_claim
    ledger = state.get("calculation_ledger")
    if (is_ordinary_civil_property_claim(str(state.get("scenario") or ""))
            and isinstance(ledger, Mapping) and ledger.get("status") == "confirmed"):
        return True
    return False


def synchronize_formula_plan(state: dict[str, Any], text: str = "", current: str | None = None, *, force: bool = False) -> dict[str, Any] | None:
    """Recompute a plan after a factual turn without choosing legal facts.

    Returns ``None`` when the conversation did not request a formula and the
    selected form has no service-owned formula to maintain.
    """
    if not force and not should_plan(state, text, current):
        return None
    before = json.dumps({"plan": state.get("calculation_plan"), "fields": state.get("fields")}, ensure_ascii=False, sort_keys=True, default=str)
    rule_ids = _rule_ids(state, text)
    if rule_ids:
        _capture_rule_facts(state, text, current, rule_ids)
    facts = _plan_facts(state)
    # New and migrated live interviews opt into the official source resolver.
    # Plain in-memory unit states remain deterministic unless they explicitly
    # request it, which keeps calculations testable without a network.
    if state.get("official_rate_lookup") is True and rule_ids:
        from app.services.document_formula_rate_resolver import resolve_official_rate_data
        resolved = resolve_official_rate_data(rule_ids, facts, state.get("fields") or {})
        if resolved:
            facts = _deep_merge(facts, resolved)
            state["rate_data"] = _deep_merge(
                state.get("rate_data") if isinstance(state.get("rate_data"), Mapping) else {},
                resolved,
            )
    plan = build_calculation_plan(
        state.get("scenario"),
        fields=state.get("fields"),
        calculation_ledger=state.get("calculation_ledger"),
        text=text,
        current=current,
        # A direct request such as "посчитайте неустойку" must return the
        # requested calculation without being held hostage by an unrelated
        # later procedural calculation (for example, state duty).  Service-
        # owned defaults are still applied on ordinary factual turns, when
        # there is no explicit formula request.
        requested=rule_ids or None,
        facts=facts,
        existing_plan=state.get("calculation_plan"),
    )
    # ``apply_plan_to_state`` can redirect a pending calculation from the
    # originating field to an actual template slot (for example, from a
    # pretense's ``amount`` to ``requests``).  Return that persisted plan so
    # the caller reports the same active field that the next interview turn
    # will use.
    plan = apply_plan_to_state(state, plan)
    after = json.dumps({"plan": state.get("calculation_plan"), "fields": state.get("fields")}, ensure_ascii=False, sort_keys=True, default=str)
    if before != after:
        state["revision"] = state.get("revision", 0) + 1
    return plan


def collect_formula_turn(state: dict[str, Any], text: str, current: str | None) -> set[str]:
    """Consume a formula request before generic consultation can misroute it.

    The caller still runs normal field intake for ordinary answers.  A pending
    plan marks a real existing form field incomplete, so the next question is
    the factual input needed by that formula rather than a request for a law
    citation or a manually calculated total.
    """
    # Auto-maintained plans such as the annual price of fixed alimony are
    # synchronised after the normal money field is saved.  Intercepting that
    # ordinary answer here would mark the empty field incomplete before its
    # value reached the intake layer.
    # Do not call a remembered unresolved rule an "explicit" request.  A
    # person may be answering the next ordinary field while an old formula is
    # pending, and that answer must reach normal intake unless it is the
    # actual formula slot.  The full set (including pending rules) is still
    # used by ``synchronize_formula_plan`` once the proper slot is reached.
    direct = detect_requested_rules(str(state.get("scenario") or ""), text)
    existing = state.get("calculation_plan")
    pending = (
        isinstance(existing, Mapping)
        and existing.get("status") in {NEEDS_INPUT, REVIEW_REQUIRED}
        and not existing.get("deferred")
    )
    pending_field = str(existing.get("current_field") or "") if isinstance(existing, Mapping) else ""
    remembered = {
        str(item) for item in state.get("formula_requested_rules", ())
        if isinstance(item, str)
    }
    explicit = direct | (remembered if not pending else set())

    # A completed calculation is history, not a conversation mode.  It must
    # never consume the next ordinary answer (name, address, contract, etc.).
    # A non-explicit answer is treated as formula input only when the current
    # question is an actual calculation slot and the stored plan is waiting
    # for it.
    if not explicit and not (
        pending
        and current in _FORMULA_REPLY_FIELDS
        # Never swallow an ordinary answer in a shared form field while the
        # plan is actually waiting for another factual slot.  Older plans may
        # not carry ``current_field``; those retain the historical behaviour.
        and (not pending_field or pending_field == current)
    ):
        return set()

    # A bare listed amount such as "неустойка - 5 000 рублей" is evidence of
    # a claimed component, not a request to choose its legal basis.  Let the
    # source-bound component ledger preserve it and ask the ordinary factual
    # follow-up.  Named legal formulas and an express request to calculate are
    # still handled here.
    if (explicit <= {"interest_basis", "penalty_basis"}
            and not pending
            and not _DIRECT_CALCULATION.search(text or "")):
        return set()
    plan = synchronize_formula_plan(state, text, current)
    if plan is None:
        return set()
    if plan.get("status") in {NEEDS_INPUT, REVIEW_REQUIRED}:
        return {str(plan.get("current_field") or current or "calculation")}
    # A completed formula must not fall through to the generic prose help
    # branch; it is a deterministic answer even when it lives in a template
    # that has no visible ``calculation`` field.
    if plan.get("status") == CALCULATED:
        return {str(plan.get("current_field") or current or "calculation")}
    return set()
