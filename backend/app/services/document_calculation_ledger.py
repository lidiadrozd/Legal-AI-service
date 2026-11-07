"""Source-bound arithmetic for monetary document requirements.

The interview stores the *facts* behind a calculation, rather than asking a
person to turn them into legal prose or to add numbers by hand.  This module
only performs transparent arithmetic on amounts explicitly supplied by the
user.  It deliberately does not invent a penalty, interest, moral-damage
amount, or a claim price: those all require a legal basis and, in many cases,
additional facts.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
from typing import Any, Callable


# A currency marker is optional here because people commonly answer a question
# about an amount with ``128500 ущерб, 7000 оценка``.  The parser only accepts
# an unmarked number when a nearby monetary component identifies what it is.
_NUMBER = r"(?:\d{1,3}(?:[ \u00a0]\d{3})+|\d+)(?:[.,]\d{1,2})?"
_AMOUNT = re.compile(
    rf"(?<![\w\d/№])(?P<number>{_NUMBER})\s*"
    r"(?P<scale>тыс\.?|тысяч(?:а|и)?|млн\.?)?\s*"
    r"(?P<currency>руб(?:лей|ля|ль|\.)?|₽)?(?![\w\d/])",
    re.IGNORECASE,
)
_DATE = re.compile(r"\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b")
_LEGAL_REFERENCE = re.compile(r"\b(?:стат(?:ья|ье|ьи|ью|ей)|ст\.|пункт|п\.|часть|ч\.)\s*\d+(?:[.,]\d+)?", re.IGNORECASE)
_COMPUTE_REQUEST = re.compile(r"\b(?:слож\w*|посчита\w*|рассчита\w*|подсчита\w*)\b", re.IGNORECASE)

# The first matching label nearest to a number gives the number its meaning.
# These are descriptive categories, not legal conclusions.  In particular,
# an item called "неустойка" is not accepted as a legally correct penalty; it
# merely preserves that the user named it and leaves the legal calculation for
# the template/rules layer.
_CATEGORIES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("total", "Итого", re.compile(r"\b(?:итого|всего|общ(?:ая|ую)\s+сумм\w*|итогов\w*\s+сумм\w*|к\s+взысканию)\b", re.I)),
    ("moral", "Компенсация морального вреда", re.compile(r"\bморал\w*\s+(?:вред\w*|ущерб\w*|компенсац\w*)|\bкомпенсац\w*\s+морал", re.I)),
    ("valuation", "Расходы на оценку", re.compile(r"\b(?:оценк\w*|оценщик\w*|эксперт(?:из\w*)?|смет\w*|диагностик\w*)", re.I)),
    ("expenses", "Дополнительные расходы", re.compile(r"\b(?:расход\w*|представител\w*|юрист\w*|адвокат\w*|нотариус\w*|почтов\w*|доставк\w*)", re.I)),
    ("penalty", "Неустойка", re.compile(r"\b(?:неустойк\w*|штраф\w*|пен[яеи]\w*)", re.I)),
    ("interest", "Проценты", re.compile(r"\bпроцент\w*", re.I)),
    ("damage", "Имущественный ущерб", re.compile(r"\b(?:ущерб\w*|убыт(?:ок|к\w*)|восстановлен\w*|ремонт\w*)", re.I)),
    ("principal", "Основная сумма требования", re.compile(r"\b(?:основн\w*\s+(?:долг\w*|сумм\w*)|задолженн\w*|долг\w*|стоимост\w*|цен[аы]\b|оплат[аы]\b)", re.I)),
)
# An appraisal is evidence for a repair-cost amount, not necessarily a second
# "assessment expense".  Keep that distinction before the generic nearest
# keyword matcher sees the word "оценщик" in the same sentence.
_DAMAGE_AMOUNT_CONTEXT = re.compile(
    r"\b(?:стоимост\w*|цен\w*|размер\w*|сумм\w*)\s+(?:восстановительн\w*\s+)?ремонт\w*|"
    r"\bвосстановительн\w*\s+ремонт\w*\s+(?:составля\w*|на\s+сумм\w*)|"
    r"\b(?:размер\w*|сумм\w*)\s+(?:имущественн\w*\s+)?ущерб\w*|"
    r"\b(?:имущественн\w*\s+)?ущерб\w*\s+(?:составля\w*|на\s+сумм\w*)|"
    r"\bубыт\w*\s+(?:составля\w*|на\s+сумм\w*)",
    re.I,
)
_PRIMARY_KINDS = {"damage", "principal"}
_ANCILLARY_COST_KINDS = {"expenses", "valuation", "court_cost", "representative_cost"}
_FORMULA_INPUT_RULE_IDS = {
    "civil_395", "contract_interest", "contract_penalty", "consumer_delay_penalty",
    "labor_delay_236", "alimony_penalty", "interest_basis", "penalty_basis",
}
_CALCULATION_INPUT_FIELDS = {
    "amount", "calculation", "costs", "litigation_costs", "penalty_calculation",
    "period_payments", "additional_claims",
}
_FRAGMENT_SEPARATOR = re.compile(
    r"[;,\n]+|[!?](?=\s)|\.(?=\s+(?:[А-ЯЁA-Z]|\d{1,2}[./]))"
)


def is_calculation_request(text: str) -> bool:
    """Whether a user asks the assistant to do arithmetic, not merely asks a question."""
    return bool(_COMPUTE_REQUEST.search(text or ""))


def calculation_help() -> str:
    """A deterministic explanation usable when the provider is unavailable."""
    return (
        "Я могу сам сложить подтверждённые суммы и оформить расчёт. Напишите каждую составляющую отдельно, "
        "например: «ущерб — 128 500 рублей, оценка — 7 000 рублей». Для процентов или неустойки нужны "
        "основание, период просрочки, ставка и уже уплаченные суммы. Компенсацию морального вреда нельзя "
        "назначить автоматически: её сумму выбирает заявитель, а окончательный размер определяет суд."
    )


def _decimal(raw: str, scale: str | None) -> str | None:
    try:
        value = Decimal(raw.replace("\u00a0", "").replace(" ", "").replace(",", "."))
        if scale:
            value *= Decimal("1000000") if scale.casefold().startswith("млн") else Decimal("1000")
        if value <= 0 or value > Decimal("1000000000000000"):
            return None
        return format(value.quantize(Decimal("0.01")), "f")
    except InvalidOperation:
        return None


def _distance(match: re.Match[str], start: int, end: int) -> int:
    if match.end() <= start:
        return start - match.end()
    if match.start() >= end:
        return match.start() - end
    return 0


def _fragment_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    """Return the short answer fragment surrounding a monetary expression.

    A decimal point or the dots in a date are not sentence boundaries.  A
    period followed by a new sentence is.  Keeping categories inside that
    fragment prevents a later phrase such as ``проценты`` from relabelling an
    earlier, independently stated principal as interest.
    """
    left = 0
    right = len(text)
    for separator in _FRAGMENT_SEPARATOR.finditer(text):
        if separator.end() <= start:
            left = separator.end()
            continue
        if separator.start() >= end:
            right = separator.start()
            break
    return left, right


def _category_near(text: str, start: int, end: int) -> tuple[str, str] | None:
    """Return the nearest category label within one short answer fragment."""
    # Do not let a label after another listed amount describe this amount.
    fragment_start, fragment_end = _fragment_bounds(text, start, end)
    nearby = text[max(fragment_start, start - 45):min(fragment_end, end + 45)]
    offset = max(fragment_start, start - 45)
    best: tuple[int, int, str, str] | None = None
    for order, (kind, label, pattern) in enumerate(_CATEGORIES):
        for found in pattern.finditer(nearby):
            distance = _distance(found, start - offset, end - offset)
            if distance > 42:
                continue
            candidate = (distance, order, kind, label)
            if best is None or candidate < best:
                best = candidate
    return (best[2], best[3]) if best else None


def _money_evidence(text: str, match: re.Match[str]) -> str:
    # Keep a compact, literal provenance fragment.  It is not rendered in the
    # document; it lets a later correction be traced to the user's words.
    left, right = _fragment_bounds(text, match.start(), match.end())
    return text[left:right].strip(" .") or match[0]


def extract_components(text: str) -> tuple[list[dict[str, str]], list[str]]:
    """Extract labelled component sums and explicitly stated totals.

    Values without a ruble marker need a nearby label such as ``ущерб`` or
    ``оценка``.  This guards against interpreting a contract number or date as
    money while still supporting ordinary chat shorthand.
    """
    if not text:
        return [], []
    date_spans = [m.span() for m in _DATE.finditer(text)]
    legal_spans = [m.span() for m in _LEGAL_REFERENCE.finditer(text)]
    items: list[dict[str, str]] = []
    totals: list[str] = []
    for match in _AMOUNT.finditer(text):
        if any(match.start() < stop and start < match.end() for start, stop in date_spans):
            continue
        if any(match.start() < stop and start < match.end() for start, stop in legal_spans):
            continue
        # A contract rate (for example, ``0.1% per day``) is an input to a
        # legal formula, never a ruble component of the claim.
        if text[match.end():].lstrip().startswith("%"):
            continue
        value = _decimal(match["number"], match["scale"])
        if not value:
            continue
        nearby = _category_near(text, match.start(), match.end())
        marked_currency = bool(match["currency"] or match["scale"])
        if not nearby and not marked_currency:
            continue
        if nearby and nearby[0] == "total":
            totals.append(value)
            continue
        fragment_start, fragment_end = _fragment_bounds(text, match.start(), match.end())
        fragment = text[fragment_start:fragment_end]
        # "Стоимость восстановительного ремонта по отчёту оценщика" is the
        # amount of damage.  The report author is evidence, whereas a
        # separately stated payment "за оценку" is the valuation expense.
        if _DAMAGE_AMOUNT_CONTEXT.search(fragment):
            kind, label = "damage", "Имущественный ущерб"
        else:
            kind, label = nearby or ("other", "Дополнительная заявленная сумма")
        item = {"kind": kind, "label": label, "value": value, "evidence": _money_evidence(text, match)}
        # Repeated wording is normally a retry, not a second expense.  A user
        # can distinguish two equal expenses by naming them separately.
        if not any(old["kind"] == item["kind"] and old["value"] == item["value"] for old in items):
            items.append(item)
    return items, totals


def _format_money(value: str | Decimal) -> str:
    amount = Decimal(value)
    rendered = format(amount, ",.2f").replace(",", " ").rstrip("0").rstrip(".")
    return rendered.replace(".", ",") + " рублей"


def _stable_items(items: list[dict[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict) or not item.get("kind") or not item.get("value"):
            continue
        try:
            Decimal(str(item["value"]))
        except InvalidOperation:
            continue
        candidate = {
            "kind": str(item["kind"]),
            "label": str(item.get("label") or "Дополнительная заявленная сумма"),
            "value": str(item["value"]),
            "evidence": str(item.get("evidence") or ""),
        }
        # Do not double-count a repeated chat message after a retry.
        if any(old["kind"] == candidate["kind"] and old["value"] == candidate["value"] for old in result):
            continue
        result.append(candidate)
    return result


def _unpriced_component_kinds(text: str, items: list[dict[str, str]]) -> list[str]:
    """Return additional component kinds the user named without an amount."""
    present = {item["kind"] for item in items}
    result: list[str] = []
    for kind, _, pattern in _CATEGORIES:
        if kind in {"total", "damage", "principal"} or kind in present:
            continue
        if pattern.search(text):
            result.append(kind)
    return result


def _with_base_amount(state: dict[str, Any], items: list[dict[str, str]]) -> list[dict[str, str]]:
    amount = state.get("fields", {}).get("amount", {})
    if amount.get("status") != "filled" or not amount.get("value"):
        return items
    try:
        base = format(Decimal(str(amount["value"])).quantize(Decimal("0.01")), "f")
    except InvalidOperation:
        return items
    if any(item["kind"] in _PRIMARY_KINDS and Decimal(item["value"]) == Decimal(base) for item in items):
        return items
    return [{"kind": "principal", "label": "Основная сумма требования", "value": base,
             "evidence": str(amount.get("original") or amount.get("evidence") or amount["value"])}] + items


def _capture_active_amount(
    state: dict[str, Any],
    current: str | None,
    specs: set[str],
    parsed: list[dict[str, str]],
) -> bool:
    """Keep a literal principal given in the ordinary amount answer.

    A person often answers the amount question and requests a statutory
    calculation in the same sentence.  Formula intake runs before ordinary
    field intake, so without this small bridge the formula correctly asks for
    a principal that was already written.  We use the unlabelled amount only
    in the active ``amount`` field and only when it is the sole such literal;
    a named interest, penalty, or several unexplained sums remain untouched.
    """
    if current != "amount" or "amount" not in specs:
        return False
    stored = state.setdefault("fields", {}).get("amount", {})
    if isinstance(stored, dict) and stored.get("status") == "filled" and stored.get("value"):
        return False
    candidates = [item for item in parsed if item.get("kind") in _PRIMARY_KINDS]
    if not candidates:
        unnamed = [item for item in parsed if item.get("kind") == "other"]
        if len(unnamed) == 1:
            candidates = unnamed
    if len(candidates) != 1:
        return False
    candidate = candidates[0]
    from app.services.document_case_facts import set_field

    if not set_field(state, "amount", candidate["value"], candidate.get("evidence") or candidate["value"]):
        return False
    state["fields"]["amount"]["source_field"] = current
    return True


def _record_formula_costs(
    state: dict[str, Any],
    text: str,
    parsed: list[dict[str, str]],
    named_formula: set[str],
) -> None:
    """Preserve explicit ancillary costs from a turn requesting a formula.

    The formula route used to short-circuit the source-bound arithmetic route,
    which made a simultaneously stated postage or assessment expense vanish.
    These are independently named factual sums, so they can be stored without
    guessing any regulated interest or penalty amount.
    """
    if not (named_formula & _FORMULA_INPUT_RULE_IDS):
        return
    costs = [item for item in parsed if item.get("kind") in _ANCILLARY_COST_KINDS]
    if not costs:
        return
    existing = state.get("calculation_ledger")
    prior = _stable_items(existing.get("items", []) if isinstance(existing, dict) else [])
    items = _stable_items(prior + costs)
    ledger = dict(existing) if isinstance(existing, dict) else {}
    ledger.update(
        version=1,
        items=items,
        origin="user_stated_formula_components",
        evidence=text,
    )
    # Do not clear a separately detected disagreement merely because a later
    # formula request repeats a cost.  A normal new cost is confirmed as a
    # literal source fact and can be joined with the ordinary principal field.
    if ledger.get("status") not in {"needs_confirmation", "amount_conflict"}:
        ledger["status"] = "confirmed"
    ledger.pop("total", None)
    ledger.pop("calculation", None)
    state["calculation_ledger"] = ledger


def _calculation_text(items: list[dict[str, str]]) -> tuple[str, str]:
    parts = [item["label"] + " — " + _format_money(item["value"]) for item in items]
    expression = " + ".join(_format_money(item["value"]).removesuffix(" рублей") for item in items)
    total = sum((Decimal(item["value"]) for item in items), Decimal("0"))
    return (
        "Расчёт заявленных денежных требований: " + "; ".join(parts) + ". Итого: "
        + expression + " = " + _format_money(total) + ".",
        format(total.quantize(Decimal("0.01")), "f"),
    )


def calculation_is_vague(text: str) -> bool:
    """A report/reference is evidence, but it is not the calculation itself."""
    if not text:
        return False
    components, totals = extract_components(text)
    if components or totals:
        return False
    # A user-provided formula may omit the word "рублей" from every operand;
    # it is still more than a bare reference to an appraiser or estimate.
    if re.search(r"\d", text):
        return False
    return bool(re.search(r"\b(?:расч[её]т\w*|оценк\w*|оценщик\w*|эксперт(?:из\w*)?|смет\w*)\b", text, re.I))


def sanitize_calculation(state: dict[str, Any]) -> None:
    """Prevent old vague values from being exported as a completed calculation."""
    field = state.get("fields", {}).get("calculation")
    if not isinstance(field, dict) or field.get("status") != "filled":
        return
    source = str(field.get("original") or field.get("evidence") or field.get("value") or "")
    if not calculation_is_vague(source):
        return
    field.update(
        status="incomplete",
        value=None,
        original=field.get("original") or source,
        evidence=field.get("evidence") or source,
        error=("Одной ссылки на оценщика или смету недостаточно для расчёта. Укажите каждую сумму отдельно: "
               "например, ущерб, оценка, расходы; я сложу подтверждённые суммы."),
        origin="calculation_needs_components",
    )


def capture_calculation_turn(
    state: dict[str, Any],
    text: str,
    current: str | None,
    put: Callable[[str, str | None, str, str], Any],
    *,
    output_key: str = "calculation",
) -> set[str]:
    """Save a multi-component calculation from one user turn when possible.

    ``put`` is the intake layer's source-bound field writer.  The function
    returns the fields it completed; an empty set means normal intake should
    continue.  A dedicated cost/payment calculation slot may legitimately
    contain one named item, while a fresh ordinary amount answer still needs
    at least two components before it replaces that answer.
    """
    if current not in _CALCULATION_INPUT_FIELDS:
        return set()
    parsed, declared_totals = extract_components(text)
    calculation_requested = is_calculation_request(text)
    existing = state.get("calculation_ledger", {})
    prior = _stable_items(existing.get("items", []) if isinstance(existing, dict) else [])
    fields = state.setdefault("fields", {})
    known_amount = fields.get("amount", {})
    has_known_amount = known_amount.get("status") == "filled" and known_amount.get("value")
    parsed_primary = next((item for item in parsed if item["kind"] in _PRIMARY_KINDS), None)

    # "Стоимость 66 000 + моральный вред, посчитай" has not selected a
    # moral-damage amount.  Keep the consultation path for an explicit request
    # for help: it explains the legal limit and asks for the one missing
    # component without treating it as zero or publishing a partial total.
    unpriced = _unpriced_component_kinds(text, parsed)
    if current != "amount" and calculation_requested and unpriced:
        return set()

    # A fresh answer to the ordinary amount question can be a single number;
    # leave that simple case to the normal field validator.  In the calculation
    # field, one labelled primary amount can still form a complete one-line
    # calculation, while an additional amount can be combined with the known
    # base amount from the earlier question.
    can_calculate = (
        len(parsed) >= 2
        or (current != "amount" and parsed)
    )
    if not can_calculate:
        if current != "amount" and calculation_is_vague(text):
            fields[output_key] = {
                "status": "incomplete", "value": None, "original": text, "evidence": text,
                "origin": "calculation_needs_components",
                "error": ("Одной ссылки на оценщика или смету недостаточно для расчёта. Укажите суммы по отдельности "
                          "(ущерб, оценка, расходы); я сам сложу их."),
            }
            state["revision"] = state.get("revision", 0) + 1
            return {output_key}
        # "Посчитай" с одним неоценённым видом требования should remain a
        # consultation.  It must not silently treat a moral-damage request as
        # zero or as a fixed percentage.
        return set()

    # A later calculation that names another primary amount is not an
    # instruction to silently replace the previously confirmed amount or to
    # charge both sums.  Stop at the discrepancy and keep both source facts
    # available for the user's explicit correction.
    if current != "amount" and parsed_primary and has_known_amount:
        try:
            known = Decimal(str(known_amount["value"]))
            supplied = Decimal(parsed_primary["value"])
        except InvalidOperation:
            known = supplied = None
        if known is not None and supplied != known:
            state["calculation_ledger"] = {
                "version": 1, "items": _stable_items(prior + parsed), "declared_totals": declared_totals,
                "origin": "user_stated_components", "evidence": text, "status": "amount_conflict",
            }
            fields[output_key] = {
                "status": "incomplete", "value": None, "original": text, "evidence": text,
                "origin": "calculation_amount_conflict",
                "error": (f"Ранее основная сумма указана как {_format_money(known)}, а в расчёте — {_format_money(supplied)}. "
                          "Подтвердите, какую из них считать основной."),
            }
            state["revision"] = state.get("revision", 0) + 1
            return {output_key}

    # Do not replace an already completed calculation because the user was
    # asked to correct a different amount field.  Explicit edit commands use
    # the ordinary correction path instead.
    if current == "amount" and fields.get(output_key, {}).get("status") == "filled":
        return set()
    items = _stable_items(prior + parsed)
    primary = next((item for item in items if item["kind"] in _PRIMARY_KINDS), None)
    if current == "amount" and primary and not has_known_amount:
        put("amount", primary["value"], primary.get("evidence") or text, "filled")
    items = _with_base_amount(state, items)
    # An unnamed number in a multi-item statement is too ambiguous to appear
    # in a legal document.  Preserve the other facts and ask only for the
    # missing description rather than asking the user to redo the calculation.
    unnamed = [item for item in items if item["kind"] == "other"]
    state["calculation_ledger"] = {
        "version": 1, "items": items, "declared_totals": declared_totals,
        "origin": "user_stated_components", "evidence": text,
    }
    if unnamed:
        values = ", ".join(_format_money(item["value"]) for item in unnamed)
        fields[output_key] = {
            "status": "incomplete", "value": None, "original": text, "evidence": text,
            "origin": "calculation_needs_component_label",
            "error": f"Уточните, что означает сумма {values}; остальные указанные суммы сохранены.",
        }
        state["revision"] = state.get("revision", 0) + 1
        return {output_key}
    if current == "amount" and not primary and not has_known_amount:
        fields["amount"] = {
            "status": "incomplete", "value": None, "original": text, "evidence": text,
            "origin": "calculation_needs_primary_amount",
            "error": "Указаны дополнительные суммы. Какая сумма является основным долгом или имущественным ущербом?",
        }
        state["revision"] = state.get("revision", 0) + 1
        return {"amount"}
    regulated = [item for item in items if item["kind"] in {"interest", "penalty"}]
    if regulated:
        labels = ", ".join(item["label"].lower() for item in regulated)
        fields[output_key] = {
            "status": "incomplete", "value": None, "original": text, "evidence": text,
            "origin": "calculation_needs_legal_inputs",
            "error": (f"Для позиции «{labels}» нужны основание, период просрочки, применяемая ставка и сведения об оплатах. "
                      "Я не добавляю такую сумму автоматически без этих данных."),
        }
        state["revision"] = state.get("revision", 0) + 1
        return {output_key}
    summary, actual_total = _calculation_text(items)
    mismatched = next((total for total in declared_totals if Decimal(total) != Decimal(actual_total)), None)
    state["calculation_ledger"].update(total=actual_total, calculation=summary)
    if mismatched:
        state["calculation_ledger"].update(status="needs_confirmation", mismatched_total=mismatched)
        fields[output_key] = {
            "status": "incomplete", "value": None, "original": text, "evidence": text,
            "origin": "calculation_total_mismatch",
            "error": (f"По перечисленным суммам получается {_format_money(actual_total)}, а указано {_format_money(mismatched)}. "
                      "Проверьте, какую сумму или составляющую нужно исправить."),
        }
        state["revision"] = state.get("revision", 0) + 1
        return {output_key}
    put(output_key, summary, text, "filled")
    state["fields"][output_key].update(origin="source_bound_arithmetic", components=items, total=actual_total)
    state["calculation_ledger"].update(status="confirmed")
    return {output_key, "amount"} if primary and fields.get("amount", {}).get("status") == "filled" else {output_key}


def collect_calculation_turn(state: dict[str, Any], text: str, current: str | None) -> set[str]:
    """Integration entry point for every form family.

    It deliberately lives outside the clause-document collector, so every
    current or future form that has both an amount and a calculation slot uses
    the same parser.  The regular collector still owns ordinary single-number
    answers and forms that do not render a calculation section.
    """
    if not state.get("scenario"):
        return set()
    from app.services.document_scenarios import SCENARIOS
    scenario = SCENARIOS[state["scenario"]]
    # Court formulas belong to claims, pretensions and procedural documents;
    # a contract, act or power of attorney may contain a price but must not
    # acquire litigation calculations merely because the parties mention a
    # penalty clause.
    if scenario.family in {"contract", "act", "authority"}:
        return set()
    specs = {field.key for field in scenario.fields}
    parsed, _ = extract_components(text)
    # A literal list of monetary components is a fact, even where the words
    # "расходы" or "неустойка" incidentally resemble a formula request.  Save
    # it first so a court-cost or supplementary-claim answer is not replaced
    # by a generic question about legal grounds before its figures are kept.
    from app.services.document_formula_registry import detect_requested_rules
    named_formula = detect_requested_rules(state["scenario"], text)
    # Store the literal principal and independently named costs before formula
    # intake claims the turn.  This gives a same-turn Article 395 request the
    # exact debt and postage amount already supplied by the person, without
    # treating a raw interest/penalty figure as an automatic legal result.
    if named_formula & _FORMULA_INPUT_RULE_IDS:
        _capture_active_amount(state, current, specs, parsed)
        _record_formula_costs(state, text, parsed, named_formula)
    component_first = bool(parsed) and not (named_formula & {
        "civil_395", "contract_interest", "contract_penalty", "consumer_delay_penalty",
        "labor_delay_236", "alimony_penalty",
    }) and (
        len(parsed) >= 2 or current in {"calculation", "costs", "litigation_costs", "penalty_calculation", "period_payments", "additional_claims"}
    )
    if not component_first:
        # Formula requests are handled before the ordinary intake.  This
        # catches a request such as "рассчитай проценты по статье 395" in any
        # field, including a pretension whose template has no separate
        # ``calculation`` slot.  The adapter records facts, never a user-chosen
        # legal rate.
        from app.services.document_formula_intake import collect_formula_turn
        planned = collect_formula_turn(state, text, current)
        if planned:
            return planned
    if current not in _CALCULATION_INPUT_FIELDS:
        return set()
    from app.services.document_case_facts import set_field

    if current not in specs:
        return set()
    if current == "amount" and "calculation" not in specs:
        return set()
    output_key = "calculation" if "calculation" in specs else current

    def put(key: str, value: str | None, evidence: str, status: str = "filled") -> None:
        if key not in specs:
            return
        existing = state.get("fields", {}).get(key, {})
        if key != current and existing.get("status") == "filled":
            return
        set_field(state, key, value, evidence, status)
        state["fields"][key]["source_field"] = current

    changed = capture_calculation_turn(state, text, current, put, output_key=output_key)
    if changed and current in {"costs", "litigation_costs"}:
        items = state.get("calculation_ledger", {}).get("items", [])
        cost_items = [item for item in items if isinstance(item, dict) and item.get("kind") in {
            "expenses", "valuation", "court_cost", "representative_cost",
        }]
        if cost_items:
            facts = state.setdefault("calculation_facts", {})
            facts["court_costs"] = {"items": cost_items}
            requested = state.setdefault("formula_requested_rules", [])
            if "court_costs" not in requested:
                requested.append("court_costs")
    return changed
