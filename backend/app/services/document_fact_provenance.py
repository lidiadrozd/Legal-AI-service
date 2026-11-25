"""Deterministic provenance gate for facts that must never be invented.

The interview already checks model quotations while collecting answers.  This
module repeats the essential contract at the export boundary so a migrated
state, a future extractor, or a presentation composer cannot publish an
unsupported identity, address, amount, or date.

Legacy policy is deliberately explicit: a filled field with neither ``origin``
nor source metadata predates provenance tracking and is retained with
``provenance_status=legacy_unattributed``.  A field which claims a model or
other non-legacy origin is not granted that exception.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal
import re


PROVENANCE_VERSION = 1

# Names of people/organisations and their direct requisites.  Address, date and
# money fields are additionally selected from the scenario schema by kind.
IDENTITY_KEYS = {
    "sender", "recipient", "employer", "seller", "buyer", "signature",
    "counterparty_signature", "court", "first_court", "principal",
    "agent", "worker", "customer", "contractor",
}

_MODEL_ORIGIN = re.compile(r"(?:^|_)(?:model|llm|assistant|ai)(?:_|$)", re.I)

# These values are produced by reviewed deterministic code.  They still need
# the metadata expected by ``_derivation_is_supported`` where applicable.
_DETERMINISTIC_ORIGINS = {
    "verified_rule", "verified_role_classification", "arithmetic",
    "loan_arithmetic", "service_balance_arithmetic", "source_bound_arithmetic", "calculation_plan",
    "calculation_plan_composition", "case_composition",
    "case_retained_source",
    "debt_claim_composition", "services_agreement_reference",
    "services_performance_composition", "services_due_date_reference",
    "services_violation_composition", "typed_request_composition",
    "confirmed_address_reference", "completed_address_locality", "personal_author_signature",
    "contract_personal_signature", "worker_personal_signature",
    "explicit_request_target", "multi_fact_property_presentation",
    "source_bound_attachment_list", "principal_only_confirmation",
    "response_deadline_validation", "product_vocabulary", "corrected_purchase_price",
}

_DATE_TOKEN = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}[./]\d{1,2}[./]\d{2,4}|"
    r"\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|"
    r"сентября|октября|ноября|декабря)\s+\d{4}(?:\s*г(?:ода|\.)?)?)\b",
    re.I,
)
_FULL_NAME = re.compile(r"\b[А-ЯЁ][а-яё-]+\s+[А-ЯЁ][а-яё-]+\s+[А-ЯЁ][а-яё-]+\b")
_ORGANISATION = re.compile(r"\b(?:ООО|АО|ПАО|ЗАО|ОАО|ИП|ТСЖ|ЖСК)\b\s*[«\"]?[^\n.;«\"]{2,100}[»\"]?", re.I)
_ADDRESS = re.compile(
    r"\b(?:(?:г\.?|город)\s*[А-ЯЁа-яё-]+(?:\s+[А-ЯЁа-яё-]+)?\s*,?\s*)?"
    r"(?:ул\.?|улица|проспект|пр-т|пер\.?|переулок|шоссе)\s+"
    r"[А-ЯЁа-яё0-9 .-]{2,80}?\s*,\s*(?:д\.?|дом)\s*\d+[А-ЯЁа-яё]?"
    r"(?:\s*,\s*(?:кв\.?|квартира|офис)\s*\d+[А-ЯЁа-яё]?)?",
    re.I,
)


def _text(value) -> str:
    return str(value or "").strip()


def _compact(value: str) -> str:
    return "".join(re.findall(r"[а-яёa-z0-9]+", _text(value).casefold().replace("ё", "е")))


def _user_sources(state: dict) -> list[str]:
    sources = [_text(state.get("request")), _text(state.get("context"))]
    sources.extend(_text(item) for item in state.get("user_turns", ()) if isinstance(item, str))
    for row in state.get("source_messages", ()):
        if isinstance(row, dict) and row.get("role") == "user":
            sources.append(_text(row.get("content")))
    return [source for source in dict.fromkeys(sources) if source]


def _source_values(item: dict) -> list[str]:
    values = []
    for key in ("original", "evidence"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    for value in item.get("source_quotes", ()):
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    return list(dict.fromkeys(values))


def _quote_is_linked(sources: list[str], quote: str) -> bool:
    needle = _compact(quote)
    return bool(needle and any(needle in _compact(source) for source in sources))


def _money_values(text: str) -> set[Decimal]:
    from app.services.document_money_tokens import find_money_quotes
    from app.services.document_workflow import normalize_money

    values: set[Decimal] = set()
    candidates = find_money_quotes(text)
    if not candidates and normalize_money(text) is not None:
        candidates = [text]
    for candidate in candidates:
        normalized = normalize_money(candidate)
        if normalized is not None:
            values.add(Decimal(normalized))
    return values


def _date_values(text: str) -> set[date]:
    from app.services.document_interest_395 import parse_dates

    values = set(parse_dates(text))
    for token in _DATE_TOKEN.findall(text or ""):
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", token):
            try:
                values.add(date.fromisoformat(token))
            except ValueError:
                pass
    return values


def _recorded_relative_day(state: dict, key: str, user_sources: list[str]) -> str | None:
    """Recover the day fixed during intake, including states exported by the older quote audit."""
    from app.services.document_explicit_facts import RELATIVE_DAYS, stated_document_date

    captured = state.get("fields", {}).get(key, {})
    day = captured.get("resolved_turn_date")
    accepted_words = RELATIVE_DAYS
    if not day and captured.get("origin") == "source_bound_extraction":
        # Older intake already resolved «сегодня» locally, before recording the
        # timestamp separately. A previous export may have moved it to rejected_value.
        day = captured.get("value") or captured.get("rejected_value")
        accepted_words = {"сегодня"}
    if not isinstance(day, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        return None
    try:
        date.fromisoformat(day)
    except ValueError:
        return None
    evidence = _text(captured.get("evidence"))
    if not evidence or not _quote_is_linked(user_sources, evidence):
        return None
    for source in user_sources:
        if not _quote_is_linked([source], evidence):
            continue
        if source.strip(" .!?").casefold() == evidence.strip(" .!?").casefold() in accepted_words:
            return day
        label = stated_document_date(state.get("scenario", ""), source) if key == "date" else None
        if label and label["day"].casefold() in accepted_words and re.search(r"\b" + label["day"] + r"\b", evidence, re.I):
            return day
    return None


def _identity_supported(value: str, sources: list[str]) -> bool:
    # Procedural roles are presentation metadata, not part of a person's name.
    candidate = _compact(re.sub(
        r",?\s*(?:истец|ответчик|заявитель|представитель|доверитель|продавец|покупатель|"
        r"заказчик|исполнитель|подрядчик|работник|работодатель)\s*$", "", value, flags=re.I,
    ))
    if not candidate:
        return False
    for source in sources:
        if candidate in _compact(source):
            return True
        # Intake may conservatively convert a common Russian full name from
        # dative to nominative.  Compare that deterministic conversion too.
        from app.services.document_explicit_facts import nominative_name
        for name in _FULL_NAME.findall(source):
            if candidate == _compact(nominative_name(name)):
                return True
        for organisation in _ORGANISATION.findall(source):
            if candidate == _compact(organisation):
                return True
    return False


def _address_supported(value: str, sources: list[str]) -> bool:
    from app.services.document_dialogue import normalize_address

    candidate = _compact(value)
    for source in sources:
        if candidate and candidate in _compact(source):
            return True
        variants = [source]
        if ":" in source:
            variants.append(source.split(":", 1)[1])
        for variant in variants:
            try:
                if _compact(normalize_address(variant)) == candidate:
                    return True
            except (TypeError, ValueError):
                continue
    return False


def _value_supported(kind: str, key: str, value: str, sources: list[str]) -> bool:
    if kind == "money":
        candidate = _money_values(value)
        return bool(candidate) and any(candidate <= _money_values(source) for source in sources)
    if kind == "date":
        candidate = _date_values(value)
        return bool(candidate) and any(candidate <= _date_values(source) for source in sources)
    if kind == "address":
        return _address_supported(value, sources)
    if key in IDENTITY_KEYS or key.endswith("_signature"):
        return _identity_supported(value, sources)

    # Narrative fields are included only when they contain typed sensitive
    # atoms.  Their prose may change, but each amount/date must survive from
    # the source.
    money = _money_values(value)
    dates = _date_values(value)
    if money and not any(money <= _money_values(source) for source in sources):
        return False
    if dates and not any(dates <= _date_values(source) for source in sources):
        return False
    names = set(_FULL_NAME.findall(value))
    organisations = set(_ORGANISATION.findall(value))
    addresses = set(_ADDRESS.findall(value))
    if any(not _address_supported(address, sources) for address in addresses):
        return False
    if names or organisations:
        atoms = [_compact(atom) for atom in (*names, *organisations)]
        corpus = " ".join(_compact(source) for source in sources)
        if any(atom not in corpus for atom in atoms):
            return False
    return bool(money or dates or names or organisations or addresses)


def _input_keys(item: dict) -> list[str]:
    inputs = item.get("inputs")
    if isinstance(inputs, str):
        return [inputs]
    if isinstance(inputs, (list, tuple, set)):
        return [value for value in inputs if isinstance(value, str)]
    if isinstance(inputs, dict):
        return [value for value in inputs if isinstance(value, str)]
    return []


def _derivation_is_supported(state: dict, fields: dict, key: str, item: dict) -> bool:
    origin = _text(item.get("origin"))
    if origin not in _DETERMINISTIC_ORIGINS and not origin.startswith("calculation_"):
        return False
    if origin == "completed_address_locality":
        from app.services.document_addresses import add_missing_locality
        from app.services.document_dialogue import normalize_address
        quotes = item.get('source_quotes') or []
        if len(quotes) != 2 or not all(_quote_is_linked(_user_sources(state), q) for q in quotes):
            return False
        base = item.get('address_base') or ''
        if not _address_supported(base, quotes[:1]):
            return False
        merged = add_missing_locality(base, quotes[1])
        return bool(merged and normalize_address(merged) == item.get('value'))
    if origin == "confirmed_address_reference":
        reference = item.get("address_reference") or {}
        if not isinstance(reference, dict):
            return False
        reference_key = reference.get("reference_field")
        return bool(
            item.get("confirmation") and reference_key
            and fields.get(reference_key, {}).get("status") == "filled"
            and fields[reference_key].get("value") == reference.get("reference_value")
            and item.get("value") == reference.get("value")
        )
    if origin == "explicit_request_target":
        return bool(_source_values(item))
    if origin == "corrected_purchase_price":
        from app.services.document_consumer_facts import reprice_consumer_text
        reference = item.get('price_reference') or {}
        original = _text(reference.get('value'))
        amount = fields.get('amount', {})
        sources = _user_sources(state)
        original_quotes = [q for q in _source_values(item) if _quote_is_linked(sources, q)]
        if (not state.get('scenario', '').startswith('pretense_consumer_') or not original
                or key not in {'requests', 'purchase', 'facts', 'payment_evidence'}
                or amount.get('status') != 'filled' or not _value_supported('text', key, original, original_quotes)):
            return False
        expected = reprice_consumer_text(key, original, reference.get('amount'), amount['value'])
        from app.services.document_editorial_grammar import clarify_consumer_wording
        if item.get('value') in {expected, clarify_consumer_wording(key, expected)}:
            return True
        # The approved editor can rephrase the corrected source for export.
        # Tie that wording to this exact source revision before accepting it.
        from app.services.document_drafting import draft_is_current
        edited = state.get('draft_fields', {}).get(key)
        return bool(state.get('fields', {}).get(key, {}).get('value') == expected
                    and draft_is_current(state) and edited
                    and item.get('value') == clarify_consumer_wording(key, edited))
    if origin in {"personal_author_signature", "contract_personal_signature", "worker_personal_signature"}:
        inputs = [fields.get(input_key, {}) for input_key in _input_keys(item)]
        values = [source.get("value") for source in inputs if source.get("status") == "filled"]
        return bool(values and _identity_supported(_text(item.get("value")), values))
    if origin == "loan_arithmetic":
        loan = state.get("loan_facts") or {}
        payments = loan.get("payments", [])
        if not loan.get("principal"):
            return False
        sources = _user_sources(state)
        if loan.get('no_other_payments_evidence') and not _quote_is_linked(sources, loan['no_other_payments_evidence']):
            return False
        quotations = [(loan["principal"], loan.get("principal_evidence", ""))]
        quotations.extend((entry["amount"], entry.get("evidence", "")) for entry in payments)
        if not all(_quote_is_linked(sources, quote) for _, quote in quotations):
            return False
        if any(entry.get('edited') for entry in payments):
            from app.services.document_loan_facts import _loan_values, _single_amount
            if any(_single_amount(entry.get('evidence')) != entry['amount']
                   for entry in payments if entry.get('edited')):
                return False
            return _loan_values(loan).get(key) == item.get('value')
        if key == "amount":
            balance = Decimal(loan["principal"]) - sum((Decimal(p["amount"]) for p in payments), Decimal(0))
            return balance in _money_values(str(item.get("value") or ""))
        return key in {"facts", "payments", "calculation"}
    if origin == "service_balance_arithmetic" and state.get("scenario") == "claim_debt_services":
        from app.services.document_obligation_facts import service_balance_inputs
        from app.services.document_case_composition import _money
        facts = service_balance_inputs(_user_sources(state))
        if not facts:
            return False
        total, paid, quotes = facts
        balance = total - paid
        expected = {"amount": format(balance, ".2f"),
                    "calculation": _money(total) + " − " + _money(paid) + " = " + _money(balance) + ".",
                    "payments": quotes[1] + " " + quotes[2]}
        return key in expected and item.get("value") == expected[key]
    if origin in {"arithmetic", "source_bound_arithmetic"}:
        inputs = _input_keys(item)
        return bool(
            (inputs and all(fields.get(input_key, {}).get("status") == "filled" for input_key in inputs))
            or item.get("components") or item.get("total")
            or isinstance(item.get("inputs"), dict)
        )
    if origin.startswith("calculation_") or origin in {"calculation_plan", "calculation_plan_composition"}:
        return bool(item.get("components") or state.get("calculation_plan"))
    if origin == "verified_rule":
        return bool(item.get("sources") or _input_keys(item))
    if origin in {"case_composition", "case_retained_source"}:
        return bool(item.get("composition_version"))
    # Remaining allowlisted transformations are narrowly implemented local
    # functions.  Their origin is the algorithm identifier for audit logs.
    return True


def _is_sensitive(spec, key: str, value: str) -> bool:
    if spec and spec.kind in {"money", "date", "address"}:
        return True
    if key in IDENTITY_KEYS or key.endswith("_signature"):
        return True
    return bool(
        _money_values(value) or _date_values(value) or _FULL_NAME.search(value)
        or _ORGANISATION.search(value) or _ADDRESS.search(value)
    )


def audit_sensitive_fields(state: dict, fields: dict | None = None) -> tuple[dict, list[dict]]:
    """Return an export-safe field copy and structured provenance issues.

    Unsupported values become explicit ``unknown`` fields.  The rejected text
    stays in metadata for correction and audit, but cannot reach a renderer.
    """
    from app.services.document_scenarios import SCENARIOS

    result = deepcopy(fields if fields is not None else state.get("fields", {}))
    scenario = SCENARIOS.get(state.get("scenario"))
    specs = {spec.key: spec for spec in scenario.fields} if scenario else {}
    user_sources = _user_sources(state)
    issues: list[dict] = []

    # Verify primary facts before derived values.  A signature or arithmetic
    # result must not survive merely because its fabricated input was still
    # present at the beginning of this function.
    for derived_pass in (False, True):
        for key, item in result.items():
            if not isinstance(item, dict) or item.get("status") != "filled" or not item.get("value"):
                continue
            value = _text(item.get("value"))
            spec = specs.get(key)
            if not _is_sensitive(spec, key, value):
                continue

            sources = _source_values(item)
            origin = _text(item.get("origin"))
            is_derivation = origin in _DETERMINISTIC_ORIGINS or origin.startswith("calculation_")
            if is_derivation != derived_pass:
                continue
            if spec and spec.kind == "date" and value == _recorded_relative_day(state, key, user_sources):
                item["provenance_status"] = "verified_turn_date"
                item["provenance_version"] = PROVENANCE_VERSION
                continue
            supported = bool(sources) and _value_supported(spec.kind if spec else "text", key, value, sources)
            linked = any(_quote_is_linked(user_sources, source) for source in sources)
            derivation = _derivation_is_supported(state, result, key, item)

            if supported and origin not in {"service_balance_arithmetic", "loan_arithmetic", "corrected_purchase_price"} and (linked or not _MODEL_ORIGIN.search(origin)):
                item["provenance_status"] = "verified_user_quote" if linked else "legacy_quote_unlinked"
                item["provenance_version"] = PROVENANCE_VERSION
                continue
            if derivation:
                item["provenance_status"] = "verified_deterministic_derivation"
                item["provenance_version"] = PROVENANCE_VERSION
                continue
            if not sources and not origin:
                # Backward-compatible migration for states saved before provenance
                # metadata existed.  New code must always set an origin or quote.
                item["provenance_status"] = "legacy_unattributed"
                item["provenance_version"] = PROVENANCE_VERSION
                continue

            reason = "evidence_mismatch" if sources else "missing_provenance"
            rejected = value
            item.update(
                status="unknown",
                value=None,
                rejected_value=rejected,
                provenance_status="rejected_" + reason,
                provenance_version=PROVENANCE_VERSION,
                provenance_error=reason,
                error=None,
            )
            issues.append({"field": key, "code": "unsupported_sensitive_fact", "reason": reason})
    return result, issues


def sanitize_sensitive_state(state: dict) -> tuple[dict, list[dict]]:
    result = deepcopy(state)
    from app.services.document_scenarios import SCENARIOS
    scenario = SCENARIOS.get(state.get("scenario"))
    for spec in scenario.fields if scenario else ():
        item = result.get("fields", {}).get(spec.key, {})
        if (spec.kind == "date" and item.get("status") == "unknown"
                and item.get("provenance_error") == "evidence_mismatch" and item.get("rejected_value")):
            day = _recorded_relative_day(state, spec.key, _user_sources(state))
            if day == item["rejected_value"]:
                item.update(status="filled", value=day, resolved_turn_date=day)
                item.pop("provenance_error", None)
                item.pop("rejected_value", None)
    result["fields"], issues = audit_sensitive_fields(result)
    result["fact_provenance_version"] = PROVENANCE_VERSION
    if issues:
        result["fact_provenance_issues"] = issues
    else:
        result.pop("fact_provenance_issues", None)
    return result, issues


def missing_data_placeholder(label: str) -> str:
    """Make an unknown field explicit without losing its human-readable name."""
    clean = re.sub(r"\s+", " ", _text(label)).strip(" :") or "поле"
    return f"[ДАННЫЕ ОТСУТСТВУЮТ: {clean.lower()}]"
