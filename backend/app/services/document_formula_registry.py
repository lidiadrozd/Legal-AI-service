"""Deterministic, source-bound calculation plans for document templates.

The interview layer is deliberately free to ask in ordinary language.  It
must not, however, turn an unverified legal guess into a number in a claim.
This module is the small policy boundary between those concerns:

* it recognises the *kind* of calculation requested across form families;
* it lists only the factual inputs that are still missing;
* it performs transparent Decimal arithmetic once verified inputs are given;
* it keeps a machine-readable plan which the renderer can use exactly once.

There is intentionally no HTTP client here.  Historical key rates, current
state-duty tariffs and a verified statutory consumer-rate rule are supplied by
the caller with their source metadata.  If that data is unavailable, the plan
stays incomplete/reviewable instead of inventing a legal rate.

Date intervals accepted by the optional interval evaluators are half-open:
``start`` is included and ``end`` is excluded.  The caller is responsible for
choosing the legally applicable first/last day before it reaches this module.
That convention avoids hidden off-by-one legal conclusions in the calculator.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from typing import Any, Callable, Iterable, Mapping, Sequence


PLAN_VERSION = 1
CALCULATED = "calculated"
NEEDS_INPUT = "needs_input"
REVIEW_REQUIRED = "review_required"
NOT_REQUESTED = "not_requested"

_TWO = Decimal("0.01")
_HUNDRED = Decimal("100")

# A claimant can call the same base amount either a principal debt or
# property damage.  The interview ledger and a legacy ``calculation`` slot
# are two views of one answer, so their matching base amount must not become
# two monetary demands merely because the views use different labels.
_PRIMARY_COMPONENT_KINDS = frozenset({"principal", "damage"})


@dataclass(frozen=True)
class FormulaRule:
    """A declarative entry in the shared calculation catalogue.

    ``families`` controls suggestion/detection only.  A caller can always
    explicitly request a rule; this makes the registry usable by new forms
    without another hard-coded ``if scenario == ...`` branch.
    """

    id: str
    label: str
    families: tuple[str, ...]
    source_hint: str
    evaluator: str
    aliases: tuple[str, ...] = ()


def scenario_family(scenario: str | None) -> str:
    """Return a stable coarse family for both built-in and future templates."""
    value = (scenario or "").strip().lower()
    if "alimony" in value:
        return "alimony"
    if "consumer" in value:
        return "consumer"
    if "labor" in value or "employment" in value:
        return "labor"
    if value.startswith("motion_cost"):
        return "court_costs"
    if value.startswith("motion_"):
        return "motion"
    if value.startswith("appeal_"):
        return "appeal"
    if "debt" in value or "loan" in value or "rent" in value or "supply" in value or "services" in value:
        return "debt"
    if "damage" in value or "flood" in value:
        return "damage"
    if value.startswith("claim_") or value.startswith("pretense_"):
        return "claim"
    return "other"


RULES: tuple[FormulaRule, ...] = (
    FormulaRule(
        "arithmetic_components", "Суммирование подтверждённых составляющих", ("all",),
        "Суммы и документы, указанные заявителем", "arithmetic",
    ),
    FormulaRule(
        "civil_395", "Проценты за пользование чужими денежными средствами", ("debt", "damage", "claim"),
        "Статья 395 ГК РФ; исторические ключевые ставки Банка России должны быть переданы проверенным источником.",
        "annual_rate_segments", ("395", "проценты за пользование чужими денежными средствами"),
    ),
    FormulaRule(
        "interest_basis", "Основание начисления процентов", ("debt", "damage", "claim"),
        "Основание процентов должно быть выбрано из обстоятельств: закон или условие договора.", "basis_choice",
        ("проценты",),
    ),
    FormulaRule(
        "contract_interest", "Проценты по договору", ("debt",),
        "Условие конкретного договора о процентах.", "contract_rate",
        ("проценты по договору", "договорные проценты", "процентный заём"),
    ),
    FormulaRule(
        "contract_penalty", "Договорная неустойка", ("debt", "claim"),
        "Условие конкретного договора о неустойке (ставка, период и предел).", "contract_rate",
        ("договорная неустойка", "неустойка по договору", "пеня по договору"),
    ),
    FormulaRule(
        "penalty_basis", "Основание начисления неустойки", ("debt", "claim", "damage"),
        "Основание неустойки должно быть подтверждено договором или применимой нормой.", "basis_choice",
        ("неустойка", "пеня"),
    ),
    FormulaRule(
        "consumer_delay_penalty", "Неустойка потребителя за просрочку", ("consumer",),
        "Применимая норма Закона РФ «О защите прав потребителей» и её редакция должны быть выбраны проверенным каталогом.",
        "daily_rate", ("неустойка", "пеня", "просрочка"),
    ),
    FormulaRule(
        "labor_delay_236", "Компенсация за задержку выплаты", ("labor",),
        "Статья 236 ТК РФ; ключевые ставки и применимый множитель передаются проверенным источником.",
        "labor_rate_segments", ("236", "компенсация за задержку", "задержк", "невыплат"),
    ),
    FormulaRule(
        "fixed_alimony_annual_price", "Цена иска по алиментам в твёрдой сумме", ("alimony",),
        "Пункт 3 части 1 статьи 91 ГПК РФ: годовая сумма периодических платежей.", "monthly_times_twelve",
    ),
    FormulaRule(
        "alimony_penalty", "Неустойка по алиментам", ("alimony",),
        "Применимое основание, период и ставка по каждому просроченному платежу должны быть проверены.", "daily_installments",
        ("неустойка по алимент", "115 ск", "алименты"),
    ),
    FormulaRule(
        "court_costs", "Судебные расходы", ("claim", "debt", "damage", "consumer", "labor", "motion", "appeal", "court_costs", "alimony"),
        "Подтверждённые расходы; вопрос их разумности оценивает суд.", "arithmetic",
        ("судебн", "представител", "почтов", "расход"),
    ),
    FormulaRule(
        "state_duty", "Государственная пошлина", ("claim", "debt", "damage", "consumer", "labor", "motion", "appeal", "alimony", "court_costs"),
        "Актуальный тариф и льгота по НК РФ должны быть переданы проверенным источником.", "tariff",
        ("госпошлин", "государственн.*пошлин"),
    ),
)
RULE_BY_ID = {rule.id: rule for rule in RULES}


def available_rule_ids(scenario: str | None) -> tuple[str, ...]:
    """Rules a UI may offer for a scenario without making them requested."""
    family = scenario_family(scenario)
    ids = ["arithmetic_components"]
    for rule in RULES:
        if rule.id == "arithmetic_components":
            continue
        if "all" in rule.families or family in rule.families:
            ids.append(rule.id)
    # A fixed monthly amount always needs its procedural price calculation,
    # even if the user did not know to ask for it.
    if (scenario or "") == "claim_alimony_fixed" and "fixed_alimony_annual_price" not in ids:
        ids.append("fixed_alimony_annual_price")
    return tuple(dict.fromkeys(ids))


_REQUEST_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("civil_395", re.compile(r"(?:(?:стать[яеёи]|ст\.)\s*395\s*(?:гк|гражданск)|395\s*(?:гк|гражданск)|процент\w*\s+за\s+пользовани\w*\s+чужими\s+денежными)", re.I)),
    ("contract_interest", re.compile(r"(?:процент\w*\s+по\s+договор|договорн\w*\s+процент|процентн\w*\s+за[её]м)", re.I)),
    ("contract_penalty", re.compile(r"(?:договорн\w*\s+(?:неустойк|пен[яеи])|(?:неустойк|пен[яеи])\w*\s+по\s+договор)", re.I)),
    ("labor_delay_236", re.compile(r"(?:(?:стать[яеёи]|ст\.)\s*236\s*тк|236\s*тк|компенсац\w*\s+за\s+задержк|компенсац\w*\s+за\s+невыплат)", re.I)),
    ("court_costs", re.compile(r"(?:судебн\w*\s+расход|расход\w*\s+на\s+(?:представител|юрист|адвокат)|почтов\w*\s+расход)", re.I)),
    ("state_duty", re.compile(r"(?:госпошлин|государственн\w*\s+пошлин)", re.I)),
)
_GENERIC_PENALTY = re.compile(r"\b(?:неустойк\w*|пен[яеи]\w*|штраф\w*)", re.I)


def _has_statutory_delay_interest_request(text: str) -> bool:
    """Whether one factual clause expressly asks for statutory delay interest.

    A bare request for ``проценты`` remains intentionally neutral: it may
    refer to a contractual rate or to Article 395.  Conversely, wording such
    as ``проценты за просрочку по закону`` already answers that legal-basis
    question.  Keep the three signals in the same short clause so an
    unrelated mention elsewhere in a long answer cannot turn a generic
    interest request into an Article 395 calculation.
    """
    for clause in re.split(r"[;!?\n]+|\.(?=\s+(?:[А-ЯЁA-Z]|\d{1,2}[./]))", text or ""):
        if not re.search(r"\bпроцент\w*", clause, re.I):
            continue
        # People do not have to use the legal word "просрочка".  Ordinary
        # wording such as "нарушение срока оплаты" describes the same factual
        # basis for a request for statutory delay interest.  Keep the signal in
        # the same clause as the request for interest and the reference to law
        # so an unrelated mention of a deadline cannot choose Article 395.
        if not re.search(
            r"\bпросроч\w*|\bнарушени\w*\s+(?:срок\w*\s+)?(?:оплат\w*|исполнени\w*)|"
            r"\b(?:срок\w*\s+)?(?:оплат\w*|исполнени\w*)\s+нарушен\w*",
            clause,
            re.I,
        ):
            continue
        if re.search(r"\b(?:по|согласно)\s+закону\b|\bзаконн\w*|\b(?:гк|гражданск\w*)", clause, re.I):
            return True
    return False


def detect_requested_rules(scenario: str | None, text: str | None) -> set[str]:
    """Find named calculation requests without deciding their legal basis.

    A bare request for a penalty is routed by document family.  It does not
    choose a rate: the evaluator will request the contractual or verified
    statutory input later.
    """
    source = text or ""
    source = re.sub(r'[^.!?;]*\b(?:не заявляю|не требую|не прошу)\b[^.!?;]*','',source,flags=re.I)
    found = {rule_id for rule_id, pattern in _REQUEST_PATTERNS if pattern.search(source)}
    if re.search(r'(?:в договоре|по договору|договор предусматривает)[^.!?;]{0,80}(?:неустойк|пени)',source,re.I):
        found.add('contract_penalty')
    family = scenario_family(scenario)
    # An explicit request for delay interest *by law* supplies the otherwise
    # ambiguous legal basis for Article 395.  Do not override an equally
    # explicit contractual-interest request; that requires the contract rate.
    if family in {"debt", "damage", "claim"} and "contract_interest" not in found:
        if _has_statutory_delay_interest_request(source):
            found.add("civil_395")
    if _GENERIC_PENALTY.search(source):
        if family == "consumer":
            found.add("consumer_delay_penalty")
        elif family == "labor":
            found.add("labor_delay_236")
        elif family == "alimony":
            found.add("alimony_penalty")
        elif "contract_penalty" in found:
            pass
        else:
            found.add("penalty_basis")
    # A generic "проценты" is ambiguous.  Do not automatically decide it is
    # Article 395 or a contractual rate; the ordinary interview asks one
    # neutral clarification unless the user named the basis.
    if re.search(r"\bпроцент\w*", source, re.I) and family in {"debt", "damage", "claim"}:
        if not {"civil_395", "contract_interest"} & found:
            found.add("interest_basis")
    return found


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    text = str(value).strip().replace("\u00a0", " ")
    if not text:
        return None
    # The helper receives structured values; accepting prose such as
    # ``120 000 рублей`` is convenient, but accepting arbitrary phrases is
    # not.  A single numeric token with standard separators is enough.
    found = re.fullmatch(r"\s*([+-]?[\d ]+(?:[,.]\d{1,4})?)\s*(?:руб(?:\.|лей|ля|ль)?|₽)?\s*", text, re.I)
    if not found:
        return None
    try:
        return Decimal(found.group(1).replace(" ", "").replace(",", "."))
    except InvalidOperation:
        return None


def _money(value: Decimal | str | int | float) -> str:
    amount = Decimal(str(value)).quantize(_TWO, rounding=ROUND_HALF_UP)
    rendered = format(amount, ",.2f").replace(",", " ").rstrip("0").rstrip(".")
    return rendered.replace(".", ",") + " рублей"


def _value(value: Decimal) -> str:
    return format(value.quantize(_TWO, rounding=ROUND_HALF_UP), "f")


def _percent(value: Decimal | str | int | float) -> str:
    rendered = format(Decimal(str(value)).normalize(), "f").replace(".", ",")
    return rendered + " %"


def _pretense_item_label(item: Mapping[str, Any]) -> str:
    """Return a document-ready name for a confirmed recovery component.

    The calculation engine intentionally uses stable machine kinds. A
    pretension is read by a person, so it must name the component rather than
    show an opaque internal label. Unknown future kinds retain their typed
    label instead of being reclassified here.
    """
    kind = str(item.get("kind") or "")
    names = {
        "principal": "основной долг",
        "damage": "сумма ущерба",
        "interest": "проценты за пользование чужими денежными средствами",
        "penalty": "неустойка",
        "consumer_penalty": "неустойка",
        "labor_compensation": "компенсация за задержку выплаты",
        "alimony_penalty": "неустойка по алиментам",
        "valuation": "расходы на оценку",
        "representative_cost": "расходы на представителя",
        "court_cost": "судебные расходы",
    }
    if kind in names:
        return names[kind]
    label = str(item.get("label") or "дополнительные расходы").strip().rstrip(".")
    evidence = str(item.get("evidence") or "").casefold()
    if kind == "expenses" and re.search(r"почтов|отправк", evidence):
        return "почтовые расходы"
    return label[:1].lower() + label[1:]


def _pretense_calculated_request(plan: Mapping[str, Any], lines: Sequence[str], *, has_user_base: bool) -> str:
    """Compose one concise, source-bound monetary paragraph for any pretension.

    The legal demand, calculated components, total and arithmetic stay
    together. The wording is driven by plan items rather than a scenario name,
    so future pretension templates receive the same protection from raw
    formula fragments and omitted totals.
    """
    components = [
        item for item in plan.get("items", ())
        if isinstance(item, Mapping)
        and item.get("include_in_recovery_total")
        and str(item.get("kind") or "") != "state_duty"
    ]
    if not components:
        return ""
    rendered = [f"{_pretense_item_label(item)} — {_money(item['value'])}" for item in components]
    try:
        total = Decimal(str(plan.get("recovery_total")))
    except (InvalidOperation, TypeError, ValueError):
        total = sum((Decimal(str(item["value"])) for item in components), Decimal("0"))
    opening = "Расчёт суммы требования: " if has_user_base else "Требую уплатить: "
    result = opening + "; ".join(rendered) + ". Общая сумма требования составляет " + _money(total) + "."
    trace = " ".join(str(line).strip() for line in lines if str(line).strip())
    return result + (" Расчёт: " + trace if trace else "")


def _date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value or "").strip()
    for pattern in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            pass
    return None


def _field_value(fields: Mapping[str, Any] | None, *keys: str) -> Any:
    for key in keys:
        item = (fields or {}).get(key)
        if isinstance(item, Mapping):
            if item.get("status") in {"filled", "confirmed", "calculated"} and item.get("value") not in {None, ""}:
                return item.get("value")
        elif item not in {None, ""}:
            return item
    return None


def _field_text(fields: Mapping[str, Any] | None) -> str:
    chunks: list[str] = []
    for item in (fields or {}).values():
        if isinstance(item, Mapping) and item.get("status") in {"filled", "incomplete", "review_required"}:
            # Rule-generated legal text is not a new user request for money.
            # Looking at it would re-open an already settled calculation merely
            # because a statutory explanation happens to mention a percentage.
            if item.get("origin") in {"verified_rule", "assistant_review", "arithmetic", "composition_metadata", "calculation_plan", "source_bound_arithmetic"} or str(item.get("origin") or "").startswith("calculation_"):
                continue
            value = item.get("original") or item.get("evidence") or item.get("value")
            if value:
                chunks.append(str(value))
    return "\n".join(chunks)


def _normalise_item(item: Mapping[str, Any], *, index: int) -> dict[str, Any] | None:
    amount = _decimal(item.get("value", item.get("amount")))
    if amount is None or amount < 0:
        return None
    kind = str(item.get("kind") or "other")
    label = str(item.get("label") or "Дополнительная заявленная сумма")
    price_default = kind in {"principal", "damage", "interest", "penalty", "consumer_penalty", "labor_compensation", "alimony_penalty"}
    recovery_default = kind not in {"state_duty", "claim_price_reference"}
    return {
        "id": str(item.get("id") or f"component:{index}:{kind}"),
        "kind": kind,
        "label": label,
        "value": _value(amount),
        "evidence": str(item.get("evidence") or item.get("source") or ""),
        "include_in_claim_price": bool(item.get("include_in_claim_price", price_default)),
        "include_in_recovery_total": bool(item.get("include_in_recovery_total", recovery_default)),
    }


def _same_primary_component(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    """Return true only for two representations of one base claim amount.

    ``principal`` and ``damage`` are deliberately both accepted: different
    interview paths name the same repair/debt base differently.  Equal costs
    of other kinds are not collapsed here because two independently named
    postal or representative expenses may genuinely have the same value.
    """
    if str(left.get("kind") or "") not in _PRIMARY_COMPONENT_KINDS:
        return False
    if str(right.get("kind") or "") not in _PRIMARY_COMPONENT_KINDS:
        return False
    left_value = _decimal(left.get("value"))
    right_value = _decimal(right.get("value"))
    return left_value is not None and left_value == right_value


def _ledger_items(calculation_ledger: Mapping[str, Any] | None, fields: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    raw: list[Mapping[str, Any]] = []
    ledger = calculation_ledger or {}
    if isinstance(ledger.get("items"), list):
        raw.extend(item for item in ledger["items"] if isinstance(item, Mapping))
    calculation = (fields or {}).get("calculation")
    if isinstance(calculation, Mapping) and isinstance(calculation.get("components"), list):
        raw.extend(item for item in calculation["components"] if isinstance(item, Mapping))
    result: list[dict[str, Any]] = []
    for index, item in enumerate(raw, 1):
        normal = _normalise_item(item, index=index)
        if not normal:
            continue
        # Repeated message retries should not turn into a second cost.  Keep
        # two equal but separately named costs, which have distinct labels.
        duplicate = next((old for old in result if old["kind"] == normal["kind"] and old["value"] == normal["value"] and old["label"] == normal["label"]), None)
        # The durable ledger is read before the older ``calculation`` field.
        # A repair-cost answer can therefore arrive once as ``principal`` and
        # once as ``damage``.  They are not two claims when the base amount is
        # identical; retain the ledger's first, source-bound representation.
        mirrored_primary = any(_same_primary_component(old, normal) for old in result)
        if not duplicate and not mirrored_primary:
            result.append(normal)
    # A ledger may begin with an ancillary expense (for example, postage)
    # while the principal was supplied in the form's ordinary ``amount``
    # field.  Treat both facts as one calculation.  The old ``if not raw``
    # branch dropped the principal whenever any expense had been saved first,
    # which produced an understated recovery total and claim price.
    amount = _decimal(_field_value(fields, "amount"))
    if amount is not None and not any(item["kind"] in {"principal", "damage"} for item in result):
        primary = _normalise_item(
            {"id": "field:amount", "kind": "principal", "label": "Основная сумма требования", "value": amount},
            index=0,
        )
        if primary:
            result.insert(0, primary)
    return result


def _entry(rule: FormulaRule, status: str, *, inputs: Mapping[str, Any] | None = None,
           missing: Iterable[str] = (), question: str | None = None,
           items: Iterable[Mapping[str, Any]] = (), formula: str | None = None,
           evidence: Iterable[str] = (), review_reason: str | None = None,
           system_action: str | None = None) -> dict[str, Any]:
    return {
        "id": rule.id,
        "label": rule.label,
        "status": status,
        "inputs": dict(inputs or {}),
        "missing": list(missing),
        "question": question,
        "items": [dict(item) for item in items],
        "formula": formula,
        "evidence": [str(item) for item in evidence if item],
        "source_hint": rule.source_hint,
        "review_reason": review_reason,
        "system_action": system_action,
    }


def _input_question(rule_id: str, missing: Sequence[str]) -> str:
    requested = set(missing)
    if rule_id == "civil_395":
        if requested == {"end_date"}:
            return ("Укажите дату фактической оплаты либо дату, по которую нужно рассчитать проценты. "
                    "Срок оплаты уже сохранён; ключевую ставку Банка России искать или вводить не нужно.")
        if requested == {"start_date"}:
            return ("Укажите согласованный срок оплаты, чтобы определить первый день просрочки. "
                    "Ключевую ставку Банка России искать или вводить не нужно.")
        if {"start_date", "end_date"} & requested:
            return ("Чтобы рассчитать проценты за пользование чужими денежными средствами, укажите дату, когда долг "
                    "должен был быть возвращён, и дату фактической оплаты либо дату, по которую нужно считать. "
                    "Если были частичные платежи, назовите их даты и суммы.")
        return "Уточните сумму непогашенного долга и сведения о частичных платежах; ставку Банка России пользователю искать не нужно."
    if rule_id == "interest_basis":
        return ("Уточните основание процентов: это условие договора или проценты за пользование чужими денежными "
                "средствами. Если есть договорная ставка, укажите её условие; если требуется расчёт по закону, "
                "укажите даты просрочки и частичных оплат.")
    if rule_id == "contract_interest":
        return ("Укажите условие договора о процентах: ставку и период (за день, месяц или год), а также даты, "
                "за которые их нужно начислить.")
    if rule_id == "contract_penalty":
        if requested <= {'days', 'start_date', 'end_date'}:
            return 'По какую дату включительно нужно рассчитать неустойку? Ставка и срок возврата уже сохранены.'
        return ("Укажите условие договора о неустойке: ставку или фиксированную сумму, за какой период она начисляется, "
                "и даты просрочки. Неустойку нельзя назначить без условия договора или иной подтверждённой нормы.")
    if rule_id == "penalty_basis":
        return ("Уточните основание неустойки: условие договора или конкретная норма закона. Затем система запросит "
                "только нужные даты, ставку и сведения об оплатах.")
    if rule_id == "consumer_delay_penalty":
        return ("Укажите согласованный срок исполнения, дату фактического исполнения либо дату расчёта и сумму, "
                "от которой считается неустойка. Применимую норму и ставку система должна проверить сама.")
    if rule_id == "labor_delay_236":
        if requested == {"end_date"}:
            return ("Укажите дату фактической выплаты либо дату, по которую нужно рассчитать компенсацию. "
                    "Срок выплаты уже сохранён; ключевую ставку искать или вводить не нужно.")
        if requested == {"start_date"}:
            return ("Укажите дату, когда выплата должна была быть произведена, чтобы определить первый день задержки. "
                    "Ключевую ставку искать или вводить не нужно.")
        return ("Укажите дату, когда выплата должна была быть произведена, дату выплаты либо дату расчёта, "
                "и сведения о частичных выплатах. Ключевую ставку пользователю искать не нужно.")
    if rule_id == "alimony_penalty":
        return ("Укажите по каждому просроченному платежу сумму, срок уплаты, дату фактической оплаты либо дату расчёта. "
                "Основание и ставку неустойки система проверит отдельно.")
    if rule_id == "state_duty":
        return "Укажите цену иска или вид требования; актуальный тариф и возможную льготу система должна сверить по проверенному источнику."
    if rule_id == "fixed_alimony_annual_price":
        return "Укажите ежемесячную сумму алиментов, которую просите взыскать."
    if rule_id == "court_costs":
        return "Перечислите судебные расходы по отдельности и укажите сумму каждого расхода."
    return "Укажите недостающие подтверждённые суммы и даты для расчёта."


def _as_rule_facts(facts: Mapping[str, Any], rule_id: str) -> dict[str, Any]:
    """Merge common facts with a rule-specific object, without mutation."""
    result = {key: value for key, value in facts.items() if not isinstance(value, Mapping)}
    specific = facts.get(rule_id)
    if isinstance(specific, Mapping):
        result.update(specific)
    return result


def _rate_segments_from_facts(data: Mapping[str, Any], *, rate_key: str = "annual_rate") -> tuple[list[dict[str, Any]], str | None]:
    """Validate supplied rate segments; no source is silently treated as official."""
    records = data.get("segments") or data.get("rate_periods") or []
    if not isinstance(records, list) or not records:
        return [], "rate_periods"
    source = data.get("rate_source") or data.get("source")
    normal: list[dict[str, Any]] = []
    for index, raw in enumerate(records, 1):
        if not isinstance(raw, Mapping):
            return [], "rate_periods"
        rate = _decimal(raw.get(rate_key, raw.get("rate_percent")))
        divisor = _decimal(raw.get("day_divisor", raw.get("divisor")))
        days_value = raw.get("days")
        days = int(days_value) if isinstance(days_value, int) or (isinstance(days_value, str) and days_value.isdigit()) else None
        start = _date(raw.get("start"))
        end = _date(raw.get("end"))
        if days is None and start and end:
            days = (end - start).days
        if rate is None or rate < 0 or divisor is None or divisor <= 0 or days is None or days < 0:
            return [], "rate_periods"
        if not source and not raw.get("source"):
            return [], "unverified_rate_source"
        normal.append({
            "id": str(raw.get("id") or index), "days": days, "rate": rate,
            "divisor": divisor, "principal": _decimal(raw.get("principal")),
            "source": str(raw.get("source") or source),
        })
    return normal, None


def _annual_segment_total(principal: Decimal, segments: Sequence[Mapping[str, Any]], *, multiplier: Decimal = Decimal("1")) -> tuple[Decimal, list[str]]:
    total = Decimal("0")
    parts: list[str] = []
    for segment in segments:
        base = segment.get("principal") or principal
        if not isinstance(base, Decimal):
            base = Decimal(str(base))
        # Each historical-rate/remaining-principal interval is a separate
        # traceable component.  Rounding it before summing keeps this registry
        # consistent with the existing Article 395 source calculator and makes
        # partial-payment calculations reproducible from the rendered lines.
        value = (base * Decimal(str(segment["rate"])) / _HUNDRED * Decimal(str(segment["days"]))
                 / Decimal(str(segment["divisor"])) * multiplier).quantize(_TWO, rounding=ROUND_HALF_UP)
        total += value
        parts.append(f"{_money(base)} × {_percent(segment['rate'])} × {segment['days']} дн. / {segment['divisor']}")
    return total.quantize(_TWO, rounding=ROUND_HALF_UP), parts


def _principal(data: Mapping[str, Any], fields: Mapping[str, Any] | None) -> Decimal | None:
    return _decimal(data.get("principal", data.get("base_amount", _field_value(fields, "amount"))))


def _formula_item(rule_id: str, kind: str, label: str, amount: Decimal, *, price: bool = True,
                  recovery: bool = True, evidence: str = "") -> dict[str, Any]:
    return {
        "id": f"formula:{rule_id}", "kind": kind, "label": label, "value": _value(amount),
        "evidence": evidence, "include_in_claim_price": price, "include_in_recovery_total": recovery,
    }


def _calculate_civil_395(rule: FormulaRule, data: Mapping[str, Any], fields: Mapping[str, Any] | None) -> dict[str, Any]:
    principal = _principal(data, fields)
    missing: list[str] = []
    if principal is None or principal <= 0:
        missing.append("principal")
    # Dates may be represented in source-bound rate segments.  Require them
    # only when the caller has not already supplied explicit day counts.
    segments, segment_problem = _rate_segments_from_facts(data)
    if not segments:
        if not _date(data.get("start_date")):
            missing.append("start_date")
        if not _date(data.get("end_date")):
            missing.append("end_date")
    if missing:
        return _entry(rule, NEEDS_INPUT, inputs=data, missing=missing, question=_input_question(rule.id, missing))
    if segment_problem == "unverified_rate_source":
        return _entry(rule, REVIEW_REQUIRED, inputs=data, review_reason=("Ставка передана без проверяемого источника; "
                          "проценты по статье 395 нельзя считать по неподтверждённым данным."), system_action="verify_key_rate_history")
    if segment_problem:
        source_error = str(data.get("source_error") or "").strip()
        return _entry(rule, REVIEW_REQUIRED, inputs=data, review_reason=(source_error or "Для расчёта нужны исторические ключевые ставки "
                          "по каждому периоду и выбранный делитель дней."),
                      system_action="retry_key_rate_history" if source_error else "load_key_rate_history")
    total, parts = _annual_segment_total(principal, segments)
    item = _formula_item(rule.id, "interest", rule.label, total, evidence="; ".join(segment["source"] for segment in segments))
    return _entry(rule, CALCULATED, inputs=data, items=[item],
                  formula=" + ".join(parts) + " = " + _money(total), evidence=[segment["source"] for segment in segments])


def _calculate_basis_choice(rule: FormulaRule, data: Mapping[str, Any]) -> dict[str, Any]:
    """Keep a generic monetary word from being mistaken for a legal basis."""
    return _entry(rule, NEEDS_INPUT, inputs=data, missing=["legal_basis"], question=_input_question(rule.id, ["legal_basis"]))


def _calculate_contract_rate(rule: FormulaRule, data: Mapping[str, Any], fields: Mapping[str, Any] | None, *, kind: str) -> dict[str, Any]:
    payments = data.get('partial_payments') or []
    if payments and any(not payment.get('date') for payment in payments):
        return _entry(rule, NEEDS_INPUT, inputs=data, missing=['payment_year'], question='В каком году был частичный возврат займа? Сумма возврата и остаток долга уже сохранены.')
    fixed = _decimal(data.get("fixed_amount"))
    if fixed is not None:
        if fixed < 0:
            return _entry(rule, NEEDS_INPUT, inputs=data, missing=["fixed_amount"], question=_input_question(rule.id, ["fixed_amount"]))
        return _entry(rule, CALCULATED, inputs=data,
                      items=[_formula_item(rule.id, kind, rule.label, fixed, evidence=str(data.get("source") or ""))],
                      formula="Фиксированная сумма по условию договора: " + _money(fixed), evidence=[str(data.get("source") or "")])
    principal = _principal(data, fields)
    rate = _decimal(data.get("rate_percent"))
    days_value = data.get("days")
    days = int(days_value) if isinstance(days_value, int) or (isinstance(days_value, str) and days_value.isdigit()) else None
    period = str(data.get("rate_period") or "").lower()
    missing = []
    if principal is None or principal < 0:
        missing.append("principal")
    if rate is None or rate < 0:
        missing.append("rate_percent")
    if days is None or days < 0:
        missing.append("days")
    if period not in {"day", "daily", "день", "за день", "year", "annual", "год", "в год", "month", "monthly", "месяц", "в месяц"}:
        missing.append("rate_period")
    if missing:
        return _entry(rule, NEEDS_INPUT, inputs=data, missing=missing, question=_input_question(rule.id, missing))
    if not data.get("source") and not data.get("contract_clause"):
        return _entry(rule, REVIEW_REQUIRED, inputs=data, review_reason="Условие договора о ставке не подтверждено.", system_action="verify_contract_clause")
    if period in {"day", "daily", "день", "за день"}:
        if payments:
            from datetime import timedelta
            start, end = _date(data.get('start_date')), _date(data.get('end_date'))
            policy = data.get('payment_day_policy')
            if not start or not end or not data.get('explicit_interval'):
                return _entry(rule, NEEDS_INPUT, inputs=data, missing=['start_date','end_date'], question='Укажите период расчёта неустойки, включая конечную дату.')
            if policy not in {'same_day', 'next_day'}:
                return _entry(rule, NEEDS_INPUT, inputs=data, missing=['payment_day_policy'], question='По договору частичный платёж уменьшает долг для начисления неустойки в день поступления или со следующего дня?')
            stop = start + timedelta(days=days)
            balance, cursor, parts, total = principal, start, [], Decimal('0')
            for payment in sorted(payments, key=lambda item: item['date']):
                paid_on, paid = _date(payment['date']), _decimal(payment['amount'])
                if paid_on is None or paid is None or paid < 0 or paid > balance:
                    return _entry(rule, NEEDS_INPUT, inputs=data, missing=['partial_payments'], question='Проверьте суммы и даты частичных возвратов займа.')
                effective = paid_on + timedelta(days=1 if policy == 'next_day' else 0)
                boundary = min(stop, max(cursor, effective))
                count = (boundary-cursor).days
                if count:
                    total += balance * rate / _HUNDRED * count
                    parts.append(f'{_money(balance)} × {_percent(rate)} × {count} дн.')
                if effective >= stop:
                    cursor = stop
                    break
                balance -= paid
                cursor = boundary
            if cursor < stop:
                count = (stop-cursor).days
                total += balance * rate / _HUNDRED * count
                parts.append(f'{_money(balance)} × {_percent(rate)} × {count} дн.')
            expression = ' + '.join(parts)
        else:
            total = principal * rate / _HUNDRED * days
            expression = f"{_money(principal)} × {_percent(rate)} × {days} дн."
    elif period in {"year", "annual", "год", "в год"}:
        if payments:
            return _entry(rule, REVIEW_REQUIRED, inputs=data,
                          review_reason='Годовая ставка при частичных возвратах требует расчёта по отдельным периодам.',
                          system_action='expand_contract_payment_periods')
        divisor = _decimal(data.get("day_divisor"))
        if divisor is None or divisor <= 0:
            return _entry(rule, NEEDS_INPUT, inputs=data, missing=["day_divisor"], question=_input_question(rule.id, ["day_divisor"]))
        total = principal * rate / _HUNDRED * days / divisor
        expression = f"{_money(principal)} × {_percent(rate)} × {days} дн. / {divisor}"
    else:
        # A month is not a fixed number of days.  The interview/service must
        # expand it into actual monthly periods before deterministic math.
        return _entry(rule, REVIEW_REQUIRED, inputs=data, review_reason=("Месячная ставка требует разбивки по "
                          "конкретным календарным периодам; единый дневной делитель здесь не предполагается."),
                      system_action="expand_contract_month_periods")
    total = total.quantize(_TWO, rounding=ROUND_HALF_UP)
    item = _formula_item(rule.id, kind, rule.label, total, evidence=str(data.get("source") or data.get("contract_clause") or ""))
    return _entry(rule, CALCULATED, inputs=data, items=[item], formula=expression + " = " + _money(total),
                  evidence=[str(data.get("source") or data.get("contract_clause") or "")])


def _calculate_consumer_delay(rule: FormulaRule, data: Mapping[str, Any], fields: Mapping[str, Any] | None) -> dict[str, Any]:
    policy_error = str(data.get("consumer_policy_error") or "").strip()
    if policy_error:
        return _entry(rule, REVIEW_REQUIRED, inputs=data, review_reason=policy_error,
                      system_action="select_applicable_consumer_regime")
    purpose_field = str(data.get("consumer_policy_missing_field") or "").strip()
    if purpose_field:
        return _entry(rule, NEEDS_INPUT, inputs=data, missing=[purpose_field],
                      question=str(data.get("consumer_policy_question") or _input_question(rule.id, [purpose_field])))
    principal = _principal(data, fields)
    rate = _decimal(data.get("daily_rate_percent"))
    days_value = data.get("days")
    days = int(days_value) if isinstance(days_value, int) or (isinstance(days_value, str) and days_value.isdigit()) else None
    missing = []
    if principal is None or principal < 0:
        missing.append("principal")
    if days is None or days < 0:
        missing.append("days")
    if missing:
        return _entry(rule, NEEDS_INPUT, inputs=data, missing=missing, question=_input_question(rule.id, missing))
    if rate is None or rate < 0 or not data.get("rate_source"):
        return _entry(rule, REVIEW_REQUIRED, inputs=data, review_reason=("Не выбрана проверенная норма и ставка "
                          "неустойки для данного потребительского требования."), system_action="resolve_consumer_penalty_rule")
    total = principal * rate / _HUNDRED * days
    cap = _decimal(data.get("cap_amount"))
    capped = cap is not None and total > cap
    if capped:
        total = cap
    total = total.quantize(_TWO, rounding=ROUND_HALF_UP)
    item = _formula_item(rule.id, "consumer_penalty", rule.label, total, evidence=str(data.get("rate_source")))
    formula = f"{_money(principal)} × {_percent(rate)} × {days} дн."
    if capped:
        formula += f"; применён подтверждённый предел {_money(cap)}"
    return _entry(rule, CALCULATED, inputs=data, items=[item], formula=formula + " = " + _money(total), evidence=[str(data.get("rate_source"))])


def _calculate_labor_delay(rule: FormulaRule, data: Mapping[str, Any], fields: Mapping[str, Any] | None) -> dict[str, Any]:
    principal = _principal(data, fields)
    missing = []
    if principal is None or principal <= 0:
        missing.append("principal")
    segments, segment_problem = _rate_segments_from_facts(data, rate_key="key_rate_percent")
    if not segments:
        if not _date(data.get("start_date")):
            missing.append("start_date")
        if not _date(data.get("end_date")):
            missing.append("end_date")
    if missing:
        return _entry(rule, NEEDS_INPUT, inputs=data, missing=missing, question=_input_question(rule.id, missing))
    if segment_problem == "unverified_rate_source":
        return _entry(rule, REVIEW_REQUIRED, inputs=data, review_reason="Ключевая ставка передана без проверяемого источника.", system_action="verify_key_rate_history")
    if segment_problem:
        source_error = str(data.get("source_error") or "").strip()
        return _entry(rule, REVIEW_REQUIRED, inputs=data, review_reason=(source_error or "Для компенсации нужны ключевые ставки "
                          "по периодам и проверяемый множитель по статье 236 ТК РФ."),
                      system_action="retry_labor_delay_rates" if source_error else "load_labor_delay_rates")
    # In this rule the segment divisor is the statutory denominator supplied
    # by the verified policy (for example, 150 under the current rule), rather
    # than a guessed number hard-coded in an interview prompt.
    total, parts = _annual_segment_total(principal, segments)
    item = _formula_item(rule.id, "labor_compensation", rule.label, total, evidence="; ".join(segment["source"] for segment in segments))
    return _entry(rule, CALCULATED, inputs=data, items=[item], formula=" + ".join(parts) + " = " + _money(total),
                  evidence=[segment["source"] for segment in segments])


def _calculate_alimony_price(rule: FormulaRule, data: Mapping[str, Any], fields: Mapping[str, Any] | None) -> dict[str, Any]:
    monthly = _decimal(data.get("monthly_amount", _field_value(fields, "monthly_amount", "amount")))
    if monthly is None or monthly <= 0:
        return _entry(rule, NEEDS_INPUT, inputs=data, missing=["monthly_amount"], question=_input_question(rule.id, ["monthly_amount"]))
    total = (monthly * Decimal("12")).quantize(_TWO, rounding=ROUND_HALF_UP)
    item = _formula_item(rule.id, "claim_price_reference", rule.label, total, price=True, recovery=False)
    return _entry(rule, CALCULATED, inputs=data, items=[item], formula=f"{_money(monthly)} × 12 месяцев = {_money(total)}")


def _calculate_alimony_penalty(rule: FormulaRule, data: Mapping[str, Any], fields: Mapping[str, Any] | None) -> dict[str, Any]:
    installments = data.get("installments")
    if not isinstance(installments, list) or not installments:
        return _entry(rule, NEEDS_INPUT, inputs=data, missing=["installments"], question=_input_question(rule.id, ["installments"]))
    total = Decimal("0")
    pieces: list[str] = []
    evidence: list[str] = []
    for index, raw in enumerate(installments, 1):
        if not isinstance(raw, Mapping):
            return _entry(rule, NEEDS_INPUT, inputs=data, missing=["installments"], question=_input_question(rule.id, ["installments"]))
        debt = _decimal(raw.get("debt", raw.get("principal")))
        rate = _decimal(raw.get("daily_rate_percent"))
        days_value = raw.get("days")
        days = int(days_value) if isinstance(days_value, int) or (isinstance(days_value, str) and days_value.isdigit()) else None
        if debt is None or rate is None or days is None or debt < 0 or rate < 0 or days < 0:
            return _entry(rule, NEEDS_INPUT, inputs=data, missing=["installments"], question=_input_question(rule.id, ["installments"]))
        if not raw.get("rate_source"):
            return _entry(rule, REVIEW_REQUIRED, inputs=data, review_reason=("Неустойка по алиментам требует "
                              "проверенной ставки и основания для каждого периода."), system_action="verify_alimony_penalty_rule")
        part = debt * rate / _HUNDRED * days
        total += part
        pieces.append(f"{_money(debt)} × {_percent(rate)} × {days} дн.")
        evidence.append(str(raw["rate_source"]))
    total = total.quantize(_TWO, rounding=ROUND_HALF_UP)
    item = _formula_item(rule.id, "alimony_penalty", rule.label, total, evidence="; ".join(evidence))
    return _entry(rule, CALCULATED, inputs=data, items=[item], formula=" + ".join(pieces) + " = " + _money(total), evidence=evidence)


def _calculate_court_costs(rule: FormulaRule, data: Mapping[str, Any], components: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    entries = data.get("items") if isinstance(data.get("items"), list) else [item for item in components if item.get("kind") in {"expenses", "valuation", "court_cost", "representative_cost"}]
    costs: list[dict[str, Any]] = []
    for index, raw in enumerate(entries or [], 1):
        if not isinstance(raw, Mapping):
            continue
        normal = _normalise_item({**raw, "kind": raw.get("kind") or "court_cost", "include_in_claim_price": False}, index=index)
        if normal:
            normal["include_in_claim_price"] = False
            costs.append(normal)
    if not costs:
        return _entry(rule, NEEDS_INPUT, inputs=data, missing=["items"], question=_input_question(rule.id, ["items"]))
    total = sum((Decimal(item["value"]) for item in costs), Decimal("0")).quantize(_TWO, rounding=ROUND_HALF_UP)
    return _entry(rule, CALCULATED, inputs=data, items=costs,
                  formula=" + ".join(_money(item["value"]) for item in costs) + " = " + _money(total),
                  review_reason="Размер расходов должен быть подтверждён документами; вопрос разумности разрешает суд.")


def _tariff_amount(price: Decimal, tariff: Mapping[str, Any]) -> Decimal | None:
    """Evaluate a caller-supplied progressive tariff without storing legal rates here.

    Brackets use ``up_to`` (inclusive upper boundary or ``None``), ``base``
    and ``percent_over``.  This is deliberately data-driven because tariff
    values may change between legal editions.
    """
    brackets = tariff.get("brackets")
    if not isinstance(brackets, list) or not brackets:
        return None
    previous = Decimal("0")
    for bracket in brackets:
        if not isinstance(bracket, Mapping):
            return None
        upper_raw = bracket.get("up_to")
        upper = None if upper_raw in {None, "", "inf", "infinity"} else _decimal(upper_raw)
        base = _decimal(bracket.get("base"))
        percent = _decimal(bracket.get("percent_over"))
        if base is None or percent is None or percent < 0 or (upper is not None and upper < previous):
            return None
        if upper is None or price <= upper:
            result = base + (price - previous) * percent / _HUNDRED
            minimum = _decimal(tariff.get("minimum"))
            maximum = _decimal(tariff.get("maximum"))
            if minimum is not None:
                result = max(result, minimum)
            if maximum is not None:
                result = min(result, maximum)
            return result.quantize(_TWO, rounding=ROUND_HALF_UP)
        previous = upper
    return None


def _calculate_state_duty(rule: FormulaRule, data: Mapping[str, Any], fields: Mapping[str, Any] | None,
                          claim_price: Decimal | None) -> dict[str, Any]:
    source_error = str(data.get("source_error") or "").strip()
    if source_error:
        return _entry(rule, REVIEW_REQUIRED, inputs=data, review_reason=source_error, system_action="review_state_duty_policy")
    if data.get("exempt") is True:
        basis = str(data.get("exemption_basis") or "")
        if not basis:
            return _entry(rule, REVIEW_REQUIRED, inputs=data, review_reason="Льгота заявлена без проверенного правового основания.", system_action="verify_state_duty_exemption")
        item = _formula_item(rule.id, "state_duty", rule.label, Decimal("0"), price=False, recovery=False, evidence=basis)
        return _entry(rule, CALCULATED, inputs=data, items=[item], formula="Государственная пошлина: льгота (0 рублей).", evidence=[basis])
    fixed = _decimal(data.get("fixed_amount"))
    tariff = data.get("tariff")
    if fixed is not None:
        if not data.get("source"):
            return _entry(rule, REVIEW_REQUIRED, inputs=data, review_reason="Размер госпошлины передан без проверенного источника.", system_action="verify_state_duty_tariff")
        item = _formula_item(rule.id, "state_duty", rule.label, fixed, price=False, recovery=False, evidence=str(data["source"]))
        return _entry(rule, CALCULATED, inputs=data, items=[item], formula="Государственная пошлина: " + _money(fixed), evidence=[str(data["source"])])
    if claim_price is None:
        price_from_data = _decimal(data.get("claim_price", _field_value(fields, "claim_price")))
        claim_price = price_from_data
    if claim_price is None:
        return _entry(rule, NEEDS_INPUT, inputs=data, missing=["claim_price"], question=_input_question(rule.id, ["claim_price"]))
    if not isinstance(tariff, Mapping) or not tariff.get("source"):
        return _entry(rule, REVIEW_REQUIRED, inputs=data, review_reason=("Нет актуального проверенного тарифа государственной "
                          "пошлины для этого вида требования."), system_action="load_state_duty_tariff")
    amount = _tariff_amount(claim_price, tariff)
    if amount is None:
        return _entry(rule, REVIEW_REQUIRED, inputs=data, review_reason="Переданный тариф госпошлины неполон или имеет неподдерживаемую структуру.", system_action="validate_state_duty_tariff")
    item = _formula_item(rule.id, "state_duty", rule.label, amount, price=False, recovery=False, evidence=str(tariff["source"]))
    return _entry(rule, CALCULATED, inputs=data, items=[item], formula=f"По проверенному тарифу от цены иска {_money(claim_price)}: {_money(amount)}.", evidence=[str(tariff["source"])])


def _calculate_arithmetic(rule: FormulaRule, components: Sequence[Mapping[str, Any]], *, formula_requested: set[str]) -> dict[str, Any]:
    items = [dict(item) for item in components]
    # Avoid a raw named interest/penalty being added a second time next to its
    # formula rule.  Preserve the conflict as a review item instead of making
    # either amount silently disappear.
    regulated_kinds = {
        "civil_395": {"interest"}, "contract_interest": {"interest"},
        "contract_penalty": {"penalty"}, "consumer_delay_penalty": {"penalty", "consumer_penalty"},
        "alimony_penalty": {"penalty", "alimony_penalty"}, "labor_delay_236": {"labor_compensation"},
    }
    conflict = [item for item in items if any(item.get("kind") in kinds for key, kinds in regulated_kinds.items() if key in formula_requested)]
    if conflict:
        return _entry(rule, REVIEW_REQUIRED, inputs={"components": items}, items=[item for item in items if item not in conflict],
                      review_reason=("Одновременно указана готовая сумма регулируемого начисления и запрошен "
                                     "автоматический расчёт. Нужно подтвердить, какая сумма подлежит включению."))
    if not items:
        return _entry(rule, NOT_REQUESTED)
    total = sum((Decimal(str(item["value"])) for item in items), Decimal("0")).quantize(_TWO, rounding=ROUND_HALF_UP)
    return _entry(rule, CALCULATED, inputs={"components": items}, items=items,
                  formula=" + ".join(_money(item["value"]) for item in items) + " = " + _money(total))


def _requested_from_existing(existing_plan: Mapping[str, Any] | None) -> set[str]:
    result: set[str] = set()
    for entry in (existing_plan or {}).get("rules", []):
        if isinstance(entry, Mapping) and entry.get("id") in RULE_BY_ID and entry.get("status") != NOT_REQUESTED:
            result.add(str(entry["id"]))
    return result


def _default_requested_rules(scenario: str | None, fields: Mapping[str, Any] | None) -> set[str]:
    """Rules owned by the service rather than requiring legal vocabulary.

    A person filing a fixed-sum alimony or consumer claim should not have to
    know that price-of-claim or a duty exemption is a separate calculation.
    Ordinary property duty is deliberately *not* auto-added here: the caller
    must first load the current, verified tariff.
    """
    result: set[str] = set()
    scenario = scenario or ""
    if scenario == "claim_alimony_fixed":
        result.add("fixed_alimony_annual_price")
    if scenario in {"claim_labor_salary", "claim_labor_reinstatement", "claim_alimony_share", "order_alimony", "claim_alimony_penalty"}:
        # These exemptions are stable legal policy supplied by the controller.
        result.add("state_duty")
    if scenario.startswith("claim_consumer"):
        result.add("state_duty")
    from app.services.document_state_duty_policy import is_ordinary_civil_property_claim
    if is_ordinary_civil_property_claim(scenario):
        result.add("state_duty")
    return result


def _normalise_requested(scenario: str | None, requested: Iterable[str] | None, text: str, existing_plan: Mapping[str, Any] | None) -> set[str]:
    ids = {item for item in (requested or ()) if item in RULE_BY_ID}
    ids |= detect_requested_rules(scenario, text)
    ids |= _requested_from_existing(existing_plan)
    # A caller that explicitly asks for one formula needs an answer about that
    # formula, not an unrelated pending state-duty calculation.  Defaults are
    # applied by the ordinary interview path (``requested is None``), where
    # the service owns all managed fields together.
    if requested is None:
        ids |= _default_requested_rules(scenario, None)
    # A former neutral clarification is superseded as soon as the interview
    # knows the concrete legal basis.  It must not keep a finished formula in
    # a perpetual ``needs_input`` state after the user answered it.
    if {"civil_395", "contract_interest"} & ids:
        ids.discard("interest_basis")
    if {"contract_penalty", "consumer_delay_penalty", "alimony_penalty"} & ids:
        ids.discard("penalty_basis")
    return ids


def _aggregate(entries: Sequence[Mapping[str, Any]], *, scenario: str | None) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_primary_values: set[str] = set()
    for entry in entries:
        if entry.get("status") != CALCULATED:
            continue
        for item in entry.get("items", []):
            if not isinstance(item, Mapping):
                continue
            item_id = str(item.get("id") or "")
            if item_id and item_id in seen_ids:
                continue
            kind = str(item.get("kind") or "")
            value = _decimal(item.get("value"))
            # Persisted plans created before the ledger/slot merge can still
            # contain both names for the same base amount.  Defend the final
            # aggregate as well, so reopening such a chat cannot double the
            # price of claim or the recovery total.
            if kind in _PRIMARY_COMPONENT_KINDS and value is not None:
                key = _value(value)
                if key in seen_primary_values:
                    continue
                seen_primary_values.add(key)
            seen_ids.add(item_id)
            items.append(dict(item))
    claim_items = [item for item in items if item.get("include_in_claim_price")]
    recovery_items = [item for item in items if item.get("include_in_recovery_total")]
    claim_total = sum((Decimal(item["value"]) for item in claim_items), Decimal("0"))
    recovery_total = sum((Decimal(item["value"]) for item in recovery_items), Decimal("0"))
    fees = [item for item in items if item.get("kind") == "state_duty"]
    unresolved = [entry for entry in entries if entry.get("status") in {NEEDS_INPUT, REVIEW_REQUIRED}]
    if any(entry.get("status") == NEEDS_INPUT for entry in entries):
        status = NEEDS_INPUT
    elif any(entry.get("status") == REVIEW_REQUIRED for entry in entries):
        status = REVIEW_REQUIRED
    elif any(entry.get("status") == CALCULATED for entry in entries):
        status = CALCULATED
    else:
        status = NOT_REQUESTED
    pending = next((entry.get("question") for entry in entries if entry.get("status") == NEEDS_INPUT and entry.get("question")), None)
    return {
        "version": PLAN_VERSION,
        "scenario": scenario,
        "status": status,
        "rules": [dict(entry) for entry in entries],
        "items": items,
        "claim_price_total": _value(claim_total) if claim_items else None,
        "recovery_total": _value(recovery_total) if recovery_items else None,
        "state_duty_total": next((fee.get("value") for fee in fees), None),
        "pending_question": pending,
        "unresolved_rule_ids": [str(entry["id"]) for entry in unresolved],
    }


def build_calculation_plan(
    scenario: str | None,
    *,
    fields: Mapping[str, Any] | None = None,
    calculation_ledger: Mapping[str, Any] | None = None,
    text: str | None = None,
    current: str | None = None,
    requested: Iterable[str] | None = None,
    facts: Mapping[str, Any] | None = None,
    rate_data: Mapping[str, Any] | None = None,
    existing_plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a calculation plan from any form's state, not just ``amount``.

    ``fields`` and ``calculation_ledger`` may be passed straight from the
    workflow state.  The service resolving official rates/tariffs supplies
    ``facts``/``rate_data``; both are plain dictionaries and safe to snapshot
    in the interview state.  ``current`` is metadata for the caller and is
    retained in the plan, so a controller can ask one next factual question.

    The function has no side effects and intentionally does not parse a free
    prose amount from arbitrary fields.  Existing source-bound parsers remain
    responsible for extracting monetary components; this registry decides how
    to calculate the component once its legal/factual type is known.
    """
    all_facts: dict[str, Any] = dict(facts or {})
    if rate_data:
        # A rule-specific value wins over common rate data.  Rate data can be
        # either a mapping by rule id or common fields such as ``rate_source``.
        for key, value in rate_data.items():
            if key not in all_facts:
                all_facts[key] = value
            elif isinstance(all_facts.get(key), Mapping) and isinstance(value, Mapping):
                all_facts[key] = {**value, **all_facts[key]}
    source_text = "\n".join(part for part in (text or "", _field_text(fields)) if part)
    requested_ids = _normalise_requested(scenario, requested, source_text, existing_plan)
    components = _ledger_items(calculation_ledger, fields)
    if components:
        requested_ids.add("arithmetic_components")

    entries: list[dict[str, Any]] = []
    # Calculate simple components first, so its confirmed primary amount can
    # feed a state-duty tariff if the caller did not expose a claim-price slot.
    if "arithmetic_components" in requested_ids:
        entries.append(_calculate_arithmetic(RULE_BY_ID["arithmetic_components"], components, formula_requested=requested_ids - {"arithmetic_components"}))

    evaluators: dict[str, Callable[[], dict[str, Any]]] = {}
    for rule_id in requested_ids - {"arithmetic_components", "state_duty", "court_costs"}:
        rule = RULE_BY_ID[rule_id]
        data = _as_rule_facts(all_facts, rule_id)
        if rule_id == "civil_395":
            evaluators[rule_id] = lambda r=rule, d=data: _calculate_civil_395(r, d, fields)
        elif rule_id in {"interest_basis", "penalty_basis"}:
            evaluators[rule_id] = lambda r=rule, d=data: _calculate_basis_choice(r, d)
        elif rule_id == "contract_interest":
            evaluators[rule_id] = lambda r=rule, d=data: _calculate_contract_rate(r, d, fields, kind="interest")
        elif rule_id == "contract_penalty":
            evaluators[rule_id] = lambda r=rule, d=data: _calculate_contract_rate(r, d, fields, kind="penalty")
        elif rule_id == "consumer_delay_penalty":
            evaluators[rule_id] = lambda r=rule, d=data: _calculate_consumer_delay(r, d, fields)
        elif rule_id == "labor_delay_236":
            evaluators[rule_id] = lambda r=rule, d=data: _calculate_labor_delay(r, d, fields)
        elif rule_id == "fixed_alimony_annual_price":
            evaluators[rule_id] = lambda r=rule, d=data: _calculate_alimony_price(r, d, fields)
        elif rule_id == "alimony_penalty":
            evaluators[rule_id] = lambda r=rule, d=data: _calculate_alimony_penalty(r, d, fields)
    # Keep registry ordering stable, not insertion ordering from text patterns.
    for rule in RULES:
        evaluator = evaluators.get(rule.id)
        if evaluator:
            entries.append(evaluator())

    if "court_costs" in requested_ids:
        entries.append(_calculate_court_costs(RULE_BY_ID["court_costs"], _as_rule_facts(all_facts, "court_costs"), components))

    # State duty is evaluated last: it can use the already known, strictly
    # calculated claim price, but procedural costs themselves do not inflate it.
    if "state_duty" in requested_ids:
        price = None
        partial = _aggregate(entries, scenario=scenario)
        if partial.get("status") not in {NEEDS_INPUT, REVIEW_REQUIRED} and partial.get("claim_price_total") is not None:
            price = Decimal(str(partial["claim_price_total"]))
        if partial.get("status") in {NEEDS_INPUT, REVIEW_REQUIRED}:
            entries.append(_entry(
                RULE_BY_ID["state_duty"], NEEDS_INPUT,
                inputs=_as_rule_facts(all_facts, "state_duty"), missing=["complete_claim_price"],
                question="Сначала нужно завершить расчёт всех заявленных денежных требований; после этого система определит госпошлину по проверенному тарифу.",
            ))
        else:
            entries.append(_calculate_state_duty(RULE_BY_ID["state_duty"], _as_rule_facts(all_facts, "state_duty"), fields, price))

    plan = _aggregate(entries, scenario=scenario)
    plan["current_field"] = current
    plan["available_rule_ids"] = list(available_rule_ids(scenario))
    return plan


def plan_from_state(state: Mapping[str, Any], text: str | None = None, current: str | None = None,
                    *, facts: Mapping[str, Any] | None = None, rate_data: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Convenience adapter for ``document_workflow`` and migration paths."""
    return build_calculation_plan(
        state.get("scenario"), fields=state.get("fields"), calculation_ledger=state.get("calculation_ledger"),
        text=text, current=current, facts=facts or state.get("calculation_facts"), rate_data=rate_data or state.get("rate_data"),
        existing_plan=state.get("calculation_plan"),
    )


def managed_formula_facts(state: Mapping[str, Any]) -> dict[str, Any]:
    """Return only the statutory data that this service can safely own.

    Rates and tariffs which change over time are intentionally absent.  They
    must arrive from a verified data source.  The exemptions below are linked
    to a selected template and do not depend on a user's legal vocabulary.
    """
    scenario = str(state.get("scenario") or "")
    if scenario in {"claim_labor_salary", "claim_labor_reinstatement"}:
        return {"state_duty": {"exempt": True, "exemption_basis": "Подпункт 1 пункта 1 статьи 333.36 НК РФ."}}
    if scenario in {"claim_alimony_share", "order_alimony", "claim_alimony_fixed", "claim_alimony_penalty"}:
        return {"state_duty": {"exempt": True, "exemption_basis": "Подпункт 2 пункта 1 статьи 333.36 НК РФ."}}
    if scenario.startswith("claim_consumer"):
        # The universal consumer form calls this fact ``procedure`` while
        # specialised forms call it ``consumer_status``.  Read the factual
        # purpose from either real template field; do not infer consumer use
        # from the product name or simply from the selected scenario.
        purposes = " ".join(
            str(_field_value(state.get("fields"), key) or "")
            for key in ("consumer_status", "procedure", "purpose", "acquisition_purpose")
        ).casefold()
        business_use = re.search(r"перепродаж|предпринимател|коммерческ|бизнес|профессиональ", purposes)
        personal_use = re.search(r"личн|семейн|домашн|для\s+себя|собственн\w*\s+потреблен", purposes)
        if personal_use and not business_use:
            price = _decimal(_field_value(state.get("fields"), "amount"))
            if price is not None and price <= Decimal("1000000"):
                return {"state_duty": {"exempt": True, "exemption_basis": "Пункт 3 статьи 17 Закона РФ «О защите прав потребителей» и подпункт 4 пункта 2 статьи 333.36 НК РФ."}}
    from app.services.document_state_duty_policy import state_duty_policy
    return state_duty_policy(state)


def apply_plan_to_state(state: dict[str, Any], plan: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Persist a calculation plan and mirror only deterministic results.

    The interview layer uses this one adapter for every template family.
    It never writes a guessed monetary value: pending/review plans leave the
    visible formula field incomplete with one factual follow-up question;
    calculated plans may populate the existing calculation/claim-price/fee
    slots when that template renders them.
    """
    result = (plan_from_state(state, facts=managed_formula_facts(state)) if plan is None else dict(plan))
    state["calculation_plan"] = result
    fields = state.setdefault("fields", {})
    scenario_fields: set[str] = set()
    scenario_key = str(state.get("scenario") or "")
    if scenario_key:
        from app.services.document_scenarios import SCENARIOS
        scenario_spec = SCENARIOS.get(scenario_key)
        if scenario_spec:
            scenario_fields = {spec.key for spec in scenario_spec.fields}
    status = result.get("status")
    items = [item for item in result.get("items", ()) if isinstance(item, Mapping)]
    lines = render_calculation_lines(result)
    if status in {NEEDS_INPUT, REVIEW_REQUIRED}:
        # A service-owned state-duty check runs once the factual ledger is
        # complete.  If the only result is that another tariff/procedure is
        # required, do not replace the next ordinary question (such as the
        # requested remedy) with that review.  The plan remains on state for
        # export validation; an expressly requested calculation still uses
        # its current field and receives the review immediately.
        unresolved = set(result.get("unresolved_rule_ids") or ())
        automatic_duty_review = (
            status == REVIEW_REQUIRED
            and unresolved == {"state_duty"}
            and not result.get("current_field")
        )
        if automatic_duty_review:
            # ``collect_formula_turn`` must distinguish this passive export
            # guard from a factual formula follow-up.  Otherwise a normal
            # answer in a shared ``requests`` field would be swallowed as an
            # answer to the tariff review.
            result["deferred"] = True
            return result
        target = None
        scenario = state.get("scenario")
        if scenario:
            from app.services.document_scenarios import SCENARIOS
            target = _plan_target_field(result, SCENARIOS.get(scenario), fields)
        if target:
            question = first_pending_question(result)
            if not question:
                question = "Для этого расчёта нужны дополнительные подтверждённые исходные данные."
            previous = fields.get(target, {})
            pending = {**previous, "status": "incomplete", "value": None,
                       "origin": "calculation_plan", "error": question}
            # A person can ask for a new calculated component after already
            # naming the principal request.  Preserve that completed wording
            # while the service asks the one factual follow-up; otherwise the
            # calculation flow itself would erase the user's original remedy.
            if previous.get("status") == "filled" and previous.get("value"):
                pending["formula_base_value"] = str(previous["value"])
                if previous.get("origin"):
                    pending["formula_base_origin"] = previous.get("origin")
            fields[target] = pending
            # ``current_field`` must name the actual slot which now awaits
            # the missing formula fact.  Otherwise the next answer reaches a
            # pretense's ``requests`` field while the stored plan still says
            # ``amount`` and the formula intake correctly (but unhelpfully)
            # rejects it as an unrelated answer.
            result["current_field"] = target
        return result
    if status != CALCULATED:
        return result
    # Stable formula lines make a transparent calculation paragraph.  An
    # arithmetic-only plan has a more readable summary in its own rule, and
    # still remains deterministic.
    calculated_substantive_rules = {
        str(rule.get("id")) for rule in result.get("rules", ())
        if isinstance(rule, Mapping) and rule.get("status") == CALCULATED
    } - {"arithmetic_components", "state_duty", "fixed_alimony_annual_price"}
    existing_calculation = fields.get("calculation", {})
    preserve_source_arithmetic = (
        existing_calculation.get("origin") == "source_bound_arithmetic"
        and not calculated_substantive_rules
    )
    if ("calculation" in fields or ("calculation" in scenario_fields and lines)) and not preserve_source_arithmetic:
        calculation_value = " ".join(lines)
        # When a newly requested formula follows a completed transparent
        # arithmetic summary, show both calculations rather than replacing
        # the principal/expenses breakdown with the later interest line.
        base_calculation = str(existing_calculation.get("formula_base_value") or "").strip()
        if base_calculation:
            calculation_value = base_calculation.rstrip(". ") + ". " + calculation_value
        fields["calculation"] = {**fields.get("calculation", {}), "status": "filled",
                                 "value": calculation_value, "origin": "calculation_plan", "error": None,
                                 "components": [dict(item) for item in items]}
    elif lines and "calculation" not in scenario_fields:
        # Pretensions and procedural forms often intentionally have no
        # separate calculation paragraph.  Keep a completed deterministic
        # calculation visible in their existing monetary/request slot rather
        # than leaving it only in JSON or asking a user to rewrite the sum.
        # The wording is neutral: it records the calculation and does not add
        # a substantive remedy beyond the item that the user selected.
        available = set(fields) | scenario_fields
        target = next((key for key in ("additional_claims", "penalty_calculation", "costs", "requests")
                       if key in available), None)
        if target:
            prefix = "Расчёт заявленного денежного требования: "
            if target == "costs":
                prefix = "Расчёт судебных расходов: "
            existing = fields.get(target, {})
            existing_value = str(existing.get("value") or existing.get("formula_base_value") or "").strip()
            base_origin = str(existing.get("formula_base_origin") or existing.get("origin") or "")
            generated_origins = {
                "calculation_plan", "calculation_plan_composition", "source_bound_arithmetic",
            }
            has_user_base = bool(existing_value) and base_origin not in generated_origins and (
                bool(existing.get("formula_base_value")) or existing.get("status") == "filled"
            )
            if target == "requests" and scenario_key.startswith("pretense_"):
                calculated_text = _pretense_calculated_request(result, lines, has_user_base=has_user_base)
            else:
                calculated_text = prefix + " ".join(lines)
            # A calculated supplement must not erase a person's independently
            # selected remedy (for example, "взыскать основной долг").  Keep
            # both facts in their native order and mark the composite value so
            # the prose editor will not paraphrase its numbers away.
            if has_user_base and existing_value:
                value = existing_value.rstrip(". ") + ". " + calculated_text
                origin = "calculation_plan_composition"
            else:
                value = calculated_text
                origin = "calculation_plan"
            fields[target] = {**existing, "status": "filled",
                              "value": value, "origin": origin, "error": None,
                              "components": [dict(item) for item in items]}
    price = result.get("claim_price_total")
    if ("claim_price" in fields or "claim_price" in scenario_fields) and price is not None:
        fields["claim_price"] = {**fields.get("claim_price", {}), "status": "filled", "value": _money(Decimal(str(price))),
                                   "origin": "calculation_plan", "error": None}
    duty = next((item for item in items if item.get("kind") == "state_duty"), None)
    if ("fee" in fields or "fee" in scenario_fields) and duty is not None:
        amount = Decimal(str(duty["value"]))
        # Calculation plans can be restored from an older chat.  Make the
        # state-duty sentence safe even if its legacy evidence contained an
        # escaped catalogue URL or a source-system revision marker.
        from app.services.document_presentation import clean_legal_citation_text
        evidence = clean_legal_citation_text(str(duty.get("evidence") or ""))
        text = "Истец освобождён от уплаты государственной пошлины."
        if amount:
            text = "Государственная пошлина составляет " + _money(amount) + "."
        if evidence:
            text = text.rstrip(".") + " Основание: " + evidence.rstrip(".") + "."
        fields["fee"] = {**fields.get("fee", {}), "status": "filled", "value": text,
                         "origin": "calculation_plan", "error": None}
    return result


def _plan_target_field(plan: Mapping[str, Any], scenario: Any,
                       fields: Mapping[str, Any] | None = None) -> str | None:
    if scenario is None:
        return None
    available = {spec.key for spec in getattr(scenario, "fields", ())}
    unresolved = set(plan.get("unresolved_rule_ids") or ())
    for rule in plan.get("rules", ()):
        if not isinstance(rule, Mapping) or rule.get("id") not in unresolved:
            continue
        for key in rule.get("missing") or ():
            # ``legal_basis`` is a managed explanatory paragraph in several
            # templates.  Asking a person to fill it turns a factual interview
            # into a request for legal research.  Formula follow-ups belong in
            # a factual calculation slot instead.
            if key in available and key not in {"legal_basis", "complete_claim_price"}:
                return str(key)
    # Prefer a true calculation/request slot that has not already been
    # completed.  Pretensions deliberately use ``additional_claims`` or
    # ``requests`` instead of a dedicated calculation paragraph; sending a
    # formula follow-up back to ``amount`` there used to erase a known debt
    # and made the dialogue look unrelated to the user's question.
    candidates = (
        "calculation", "additional_claims", "penalty_calculation", "period_payments",
        "costs", "litigation_costs", "requests", "amount", "claim_price", "fee",
    )
    stored = fields or {}
    for key in candidates:
        if key not in available:
            continue
        status = (stored.get(key) or {}).get("status") if isinstance(stored.get(key), Mapping) else None
        if status not in {"filled", "unknown", "not_applicable"}:
            return key
    for key in candidates:
        if key in available:
            return key
    return None


def first_pending_question(plan: Mapping[str, Any]) -> str | None:
    """Return exactly one user-facing factual question, if the plan has one."""
    question = plan.get("pending_question")
    if question:
        return str(question)
    unresolved = set(plan.get("unresolved_rule_ids") or ())
    for rule in plan.get("rules", ()):
        if not isinstance(rule, Mapping) or rule.get("id") not in unresolved:
            continue
        reason = str(rule.get("review_reason") or "").strip()
        if reason:
            return reason
    return None


def calculation_is_blocking(plan: Mapping[str, Any]) -> bool:
    """Whether a requested calculation prevents a finished monetary draft."""
    return plan.get("status") in {NEEDS_INPUT, REVIEW_REQUIRED}


def render_calculation_lines(plan: Mapping[str, Any]) -> list[str]:
    """Return deterministic, non-duplicating text lines for a template slot."""
    lines: list[str] = []
    arithmetic_items: set[tuple[str, str, str]] = set()
    for entry in plan.get("rules", []):
        if not isinstance(entry, Mapping) or entry.get("id") != "arithmetic_components":
            continue
        for item in entry.get("items", []):
            if isinstance(item, Mapping):
                arithmetic_items.add((
                    str(item.get("kind") or ""), str(item.get("value") or ""), str(item.get("label") or ""),
                ))
    for entry in plan.get("rules", []):
        if not isinstance(entry, Mapping) or entry.get("status") != CALCULATED:
            continue
        if entry.get("id") == "state_duty":
            # State duty is a separate procedural payment, rendered only in
            # the fee slot.  It must never be added to the claim calculation.
            continue
        if entry.get("id") == "court_costs":
            # The arithmetic ledger already renders an explicit postal,
            # representative, or valuation cost.  The specialised court-cost
            # rule still owns the legal review, but rendering the same source
            # item a second time makes the resulting document look as though
            # the expense was requested twice.
            cost_items = [item for item in entry.get("items", []) if isinstance(item, Mapping)]
            if cost_items and all(
                (str(item.get("kind") or ""), str(item.get("value") or ""), str(item.get("label") or ""))
                in arithmetic_items
                for item in cost_items
            ):
                continue
        formula = str(entry.get("formula") or "").strip()
        if formula:
            data=entry.get('inputs') or {}
            if data.get('explicit_interval'):
                start,end=_date(data.get('start_date')),_date(data.get('end_date'))
                if start and end:
                    inclusive=' включительно' if data.get('days')==(end-start).days+1 else ''
                    formula=f"За период с {start:%d.%m.%Y} по {end:%d.%m.%Y}{inclusive}: "+formula
            lines.append(formula.rstrip("." ) + ".")
    return list(dict.fromkeys(lines))
