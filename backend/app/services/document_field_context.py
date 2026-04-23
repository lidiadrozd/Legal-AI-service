"""
Извлечение полей для шаблонов документов из текста чата и реквизитов подачи в суд.
Эвристики — не замена юридической проверки; пользователь может править поля вручную.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

CASE_NUMBER_RE = re.compile(
    r"(?:дело|№|N)\s*[:\s]*([АA]\d{1,2}-\d{1,6}/\d{4})",
    re.IGNORECASE,
)
CASE_NUMBER_STANDALONE_RE = re.compile(r"\b([АA]\d{1,2}-\d{1,6}/\d{4})\b", re.IGNORECASE)
ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
DMY_DATE_RE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")
ARBITR_COURT_LINE_RE = re.compile(
    r"(Арбитражный\s+суд[^\n\.]{3,120})",
    re.IGNORECASE,
)
APPEAL_COURT_RE = re.compile(
    r"((?:Девят|Восьм|Седьм|Шест|Пят|Четв[её]рт|Трет|Втор|Перв)ый\s+арбитражный\s+апелляционный\s+суд[^\n\.]{0,80})",
    re.IGNORECASE,
)
AMOUNT_RE = re.compile(
    r"(\d[\d\s]*(?:[.,]\d+)?)\s*(?:руб|рубл|₽)",
    re.IGNORECASE,
)
OOO_NAME_RE = re.compile(r"(ООО\s+[«\"]?[А-Яа-яA-Za-z0-9\s\-«»\"]{2,80}[»\"]?)")
IP_NAME_RE = re.compile(r"(ИП\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.[А-ЯЁ]\.)")


def _to_iso_date(dmy: tuple[str, str, str]) -> str:
    d, m, y = (int(dmy[0]), int(dmy[1]), int(dmy[2]))
    return date(y, m, d).isoformat()


def extract_from_text(text: str) -> dict[str, str]:
    text = (text or "").strip()
    out: dict[str, str] = {}

    m = CASE_NUMBER_RE.search(text) or CASE_NUMBER_STANDALONE_RE.search(text)
    if m:
        cn = m.group(1).upper().replace("A", "А")
        out["case_number"] = cn

    for iso in ISO_DATE_RE.findall(text):
        out.setdefault("date_iso", iso)

    dmy = DMY_DATE_RE.search(text)
    if dmy:
        try:
            iso = _to_iso_date((dmy.group(1), dmy.group(2), dmy.group(3)))
            out.setdefault("date_iso", iso)
        except ValueError:
            pass

    court_m = ARBITR_COURT_LINE_RE.search(text)
    if court_m:
        out["court_name"] = court_m.group(1).strip()
        out.setdefault("first_instance_court_name", out["court_name"])

    appeal_m = APPEAL_COURT_RE.search(text)
    if appeal_m:
        out["appeal_court_name"] = appeal_m.group(1).strip()

    amt = AMOUNT_RE.search(text)
    if amt:
        raw = amt.group(1).replace(" ", "").replace(",", ".")
        out["claim_amount"] = f"{raw} руб."

    ooo = OOO_NAME_RE.search(text)
    if ooo:
        out.setdefault("defendant_name", ooo.group(1).strip())
        out.setdefault("appellant_name", ooo.group(1).strip())

    ip = IP_NAME_RE.search(text)
    if ip:
        out.setdefault("plaintiff_name", ip.group(1).strip())

    return out


def suggest_fields_for_template(
    template_key: str,
    *,
    context_text: str,
    filing_fields: dict[str, str] | None = None,
) -> tuple[dict[str, str], dict[str, str]]:
    """
    Возвращает (suggested_fields, sources) где sources[field_key] кратко описывает происхождение значения.
    """
    filing_fields = filing_fields or {}
    extracted = extract_from_text(context_text)
    suggested: dict[str, str] = {}
    sources: dict[str, str] = {}

    if template_key == "statement_of_claim_arbitration":
        if filing_fields.get("court_name"):
            suggested["court_name"] = filing_fields["court_name"]
            sources["court_name"] = "court_filing"
        elif extracted.get("court_name"):
            suggested["court_name"] = extracted["court_name"]
            sources["court_name"] = "chat_text"
        if extracted.get("claim_amount"):
            suggested["claim_amount"] = extracted["claim_amount"]
            sources["claim_amount"] = "chat_text"
        if extracted.get("defendant_name"):
            suggested["defendant_name"] = extracted["defendant_name"]
            sources["defendant_name"] = "chat_text"
        if extracted.get("plaintiff_name"):
            suggested["plaintiff_name"] = extracted["plaintiff_name"]
            sources["plaintiff_name"] = "chat_text"
        if extracted.get("date_iso"):
            suggested["date"] = extracted["date_iso"]
            sources["date"] = "chat_text"
        else:
            suggested["date"] = date.today().isoformat()
            sources["date"] = "default_today"

    elif template_key == "motion_to_postpone_hearing":
        if filing_fields.get("court_name"):
            suggested["court_name"] = filing_fields["court_name"]
            sources["court_name"] = "court_filing"
        elif extracted.get("court_name"):
            suggested["court_name"] = extracted["court_name"]
            sources["court_name"] = "chat_text"
        if filing_fields.get("case_number"):
            cn = filing_fields["case_number"].upper().replace("A", "А")
            suggested["case_number"] = cn
            sources["case_number"] = "court_filing"
        elif extracted.get("case_number"):
            suggested["case_number"] = extracted["case_number"]
            sources["case_number"] = "chat_text"
        if extracted.get("date_iso"):
            suggested.setdefault("date", extracted["date_iso"])
            sources.setdefault("date", "chat_text")
            suggested.setdefault("hearing_date", extracted["date_iso"])
            sources.setdefault("hearing_date", "chat_text")

    elif template_key == "appeal_complaint":
        if filing_fields.get("court_name"):
            suggested["first_instance_court_name"] = filing_fields["court_name"]
            sources["first_instance_court_name"] = "court_filing"
        elif extracted.get("first_instance_court_name"):
            suggested["first_instance_court_name"] = extracted["first_instance_court_name"]
            sources["first_instance_court_name"] = "chat_text"
        if filing_fields.get("case_number"):
            cn = filing_fields["case_number"].upper().replace("A", "А")
            suggested["case_number"] = cn
            sources["case_number"] = "court_filing"
        elif extracted.get("case_number"):
            suggested["case_number"] = extracted["case_number"]
            sources["case_number"] = "chat_text"
        if extracted.get("appeal_court_name"):
            suggested["appeal_court_name"] = extracted["appeal_court_name"]
            sources["appeal_court_name"] = "chat_text"
        if extracted.get("appellant_name"):
            suggested["appellant_name"] = extracted["appellant_name"]
            sources["appellant_name"] = "chat_text"
        if extracted.get("date_iso"):
            suggested.setdefault("date", extracted["date_iso"])
            sources.setdefault("date", "chat_text")
        else:
            suggested.setdefault("date", date.today().isoformat())
            sources.setdefault("date", "default_today")

    if "date" not in suggested:
        if extracted.get("date_iso"):
            suggested["date"] = extracted["date_iso"]
            sources["date"] = "chat_text"
        else:
            suggested["date"] = date.today().isoformat()
            sources["date"] = "default_today"

    return suggested, sources


def merge_user_over_suggested(suggested: dict[str, str], user: dict[str, Any]) -> dict[str, str]:
    merged = dict(suggested)
    for key, raw in user.items():
        val = str(raw).strip()
        if val:
            merged[key] = val
    return merged
