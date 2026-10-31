"""Versioned, source-labelled state-duty policy for unambiguous civil claims.

This is data rather than arithmetic code so that a legislative change is a
small, reviewable policy update.  The shared formula registry validates and
evaluates the table; it never treats an unlabelled number as a tariff.

The catalogue deliberately covers only ordinary civil property claims.  It
does not guess an arbitrazh, appellate, mixed or non-property tariff.
"""
from __future__ import annotations

from datetime import date, datetime
import re
from typing import Any, Mapping


# A citation is printable document text.  Revision dates and repository URLs
# remain structured provenance below and must not be concatenated into it.
NK_ARTICLE_333_19 = "подпункт 1 пункта 1 статьи 333.19 НК РФ"
NK_SOURCE_URL = "https://www.consultant.ru/document/cons_doc_LAW_28165/"
EFFECTIVE_FROM = date(2024, 9, 8)

ORDINARY_CIVIL_PROPERTY_SCENARIOS = frozenset({
    "claim_debt_loan",
    "claim_debt_rent",
    "claim_debt_services",
    "claim_debt_supply",
    "claim_rent_deposit",
    "claim_damage_flood",
    "claim_damage_property",
})

ORDINARY_CIVIL_PROPERTY_TARIFF = {
    "source": NK_ARTICLE_333_19,
    "source_url": NK_SOURCE_URL,
    "effective_from": EFFECTIVE_FROM.isoformat(),
    "minimum": "4000",
    "maximum": "200000",
    "brackets": [
        {"up_to": "100000", "base": "0", "percent_over": "4"},
        {"up_to": "300000", "base": "4000", "percent_over": "3"},
        {"up_to": "500000", "base": "10000", "percent_over": "2.5"},
        {"up_to": "1000000", "base": "15000", "percent_over": "2"},
        {"up_to": "3000000", "base": "25000", "percent_over": "1"},
        {"up_to": "8000000", "base": "45000", "percent_over": "0.7"},
        {"up_to": "20000000", "base": "80000", "percent_over": "0.35"},
        {"up_to": None, "base": "122000", "percent_over": "0.1"},
    ],
}


def _as_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    for layout in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, layout).date()
        except ValueError:
            continue
    return None


def _filled(fields: Mapping[str, Any], key: str) -> str:
    item = fields.get(key, {})
    if isinstance(item, Mapping) and item.get("status") == "filled":
        return str(item.get("value") or "")
    return ""


def is_ordinary_civil_property_claim(scenario: str | None) -> bool:
    return str(scenario or "") in ORDINARY_CIVIL_PROPERTY_SCENARIOS


def state_duty_policy(state: Mapping[str, Any]) -> dict[str, Any]:
    """Return tariff facts only when the court/procedure is not ambiguous."""
    scenario = str(state.get("scenario") or "")
    if not is_ordinary_civil_property_claim(scenario):
        return {}
    fields = state.get("fields") or {}
    document_date = _as_date(_filled(fields, "date"))
    if document_date is not None and document_date < EFFECTIVE_FROM:
        return {"state_duty": {
            "source_error": "Для документа с указанной датой нужен тариф госпошлины, действовавший на дату подачи; текущая таблица автоматически не применяется.",
        }}
    procedure = " ".join((_filled(fields, "procedure"), _filled(fields, "jurisdiction"))).casefold()
    if re.search(r"арбитраж|апк|предпринимательск", procedure):
        return {"state_duty": {
            "source_error": "Для арбитражного или предпринимательского спора применяется отдельный тариф госпошлины; его нельзя заменить тарифом суда общей юрисдикции.",
        }}
    return {"state_duty": {"tariff": ORDINARY_CIVIL_PROPERTY_TARIFF}}
