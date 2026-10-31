"""Load reviewed text packages independently of interview code.

Packages are trusted application assets. Review metadata records a human review;
schema validation alone never constitutes a legal review.
"""
from datetime import date
import json
from pathlib import Path
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "templates" / "documents"
PLACEHOLDER = re.compile(r"\{\{([a-z_]+)\}\}")


class TextBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1)
    role: Literal["body", "addressee", "title", "heading", "request", "attachments", "signature", "place_date"] = "body"
    when_field: str | None = None
    when_value: str | None = None
    when_status: Literal['filled'] | None = None
    when_values: list[str] | None = None


class TextPackage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: str
    composition: Literal['questionnaire','legal_document','clause_document'] = 'questionnaire'
    intake_only_fields: list[str] = Field(default_factory=list)
    field_formats: dict[str,Literal['phrase','sentence','list','requisite','auto']] = Field(default_factory=dict)
    version: int = Field(ge=1)
    schema_version: int | None = None
    coverage: Literal['basic', 'structured'] = 'basic'
    source: str = Field(min_length=1)
    usage_basis: str = Field(min_length=1)
    review_status: Literal["source_checked_draft", "lawyer_reviewed"] = "source_checked_draft"
    checked_at: date | None = None
    reviewed_by: str | None = None
    reviewed_at: date | None = None
    layout: Literal["letter", "claim", "appeal", "contract", "act", "authority"] = "letter"
    source_urls: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    blocks: list[TextBlock] = Field(min_length=1)
    docx_asset: dict[str, str] | None = None


def load_text_package(scenario):
    path = TEMPLATE_ROOT / f"{scenario.key}.json"
    if not path.is_file():
        return None
    package = TextPackage.model_validate(json.loads(path.read_text(encoding="utf-8")))
    if package.scenario != scenario.key:
        raise ValueError("Template scenario mismatch")
    if package.review_status == "lawyer_reviewed" and (not package.reviewed_by or not package.reviewed_at):
        raise ValueError("Legal review requires a reviewer and date")
    allowed = {f.key for f in scenario.fields}
    if set(package.intake_only_fields)-allowed: raise ValueError('Unknown intake-only field')
    if set(package.field_formats)-allowed: raise ValueError('Unknown field format')
    for block in package.blocks:
        if set(PLACEHOLDER.findall(block.text)) - allowed:
            raise ValueError("Unknown template placeholder")
        if (block.when_field is None) != (block.when_value is None and block.when_status is None and block.when_values is None):
            raise ValueError("A conditional block needs both a field and value")
        if block.when_field and block.when_field not in allowed:
            raise ValueError("Unknown condition field")
    result = package.model_dump(mode="json")
    if package.schema_version and package.schema_version != scenario.version:
        raise ValueError('Template schema version mismatch')
    from app.services.document_schema import schema_issues
    issues = schema_issues(scenario, result)
    if issues: raise ValueError('Invalid document schema: ' + ', '.join(issues))
    return result


def render_text_package(package: dict, scenario, fields: dict, formatted: dict) -> str:
    return "\n\n".join(block["text"] for block in render_package_blocks(package, scenario, fields, formatted))


def format_template_fields(scenario, fields):
    from decimal import Decimal
    values = {}
    for spec in scenario.fields:
        from app.services.document_scenarios import field_is_active
        if not field_is_active(spec, fields): continue
        stored = fields.get(spec.key, {})
        if stored.get("status") == "not_applicable":
            values[spec.key] = "Отсутствуют" if spec.key in {"other_participants", "attachments"} else "Не применимо"
            continue
        if stored.get("status") != "filled" or not stored.get("value"):
            continue
        value = stored["value"]
        if spec.key == "attachments":
            value = "\n".join(line[:1].upper() + line[1:] for line in value.splitlines())
        if spec.kind == "money":
            from app.services.document_presentation import format_money
            value = format_money(value) + " рублей"
        elif spec.kind == "date":
            value = date.fromisoformat(value).strftime("%d.%m.%Y")
        from app.services.document_presentation import clean_legal_citation_text,normalize_monetary_text,normalize_prose_dates
        from app.services.document_export_contract import ROLE_FIELDS
        if spec.kind=='text' and spec.key not in ROLE_FIELDS:value=normalize_prose_dates(value)
        # The state-duty calculation records source provenance separately;
        # legacy saved plans may still have copied that metadata into ``fee``.
        # Do not alter factual or legal-basis fields here.
        if spec.key == "fee":
            value = clean_legal_citation_text(value)
        values[spec.key] = normalize_monetary_text(value)
    return values


def strip_template_label_echo(value: str, prefix: str) -> str:
    """Remove only a label that the trusted template already prints.

    A slot editor occasionally returns ``"Обстоятельства нарушения: ..."``
    even though that exact label is immediately to the left of the content
    control.  This is presentation cleanup, not prose editing: the removal
    happens only for an exact leading copy of the literal template label.
    It is shared by text and DOCX rendering so a preview cannot look correct
    while the downloaded Word file still contains a duplicated heading.
    """
    if not isinstance(value, str) or not isinstance(prefix, str):
        return value
    # A block may contain a preceding field and a second labelled field on
    # the same line.  Only the literal tail directly before the current
    # placeholder is its wrapper (for example, ``"Обстоятельства нарушения:"``).
    tail = re.split(r"\{\{[a-z_]+\}\}", prefix)[-1]
    tail = re.split(r"[.!?](?:\s+|$)", tail)[-1].strip()
    if not tail.endswith(":") or len(tail) > 180 or not re.search(r"[A-Za-zА-Яа-яЁё]", tail):
        return value
    label_pattern = r"\s+".join(re.escape(part) for part in tail.split())
    result = value
    # Be defensive about a legacy cached edit that contains the same wrapper
    # more than once.  The cap prevents an accidental loop on malformed data.
    for _ in range(3):
        matched = re.match(r"^\s*" + label_pattern + r"\s*", result, flags=re.I)
        if not matched:
            break
        result = result[matched.end():].lstrip(" \t\n—–-")
    return result


def render_package_blocks(package: dict, scenario, fields: dict, formatted: dict) -> list[dict]:
    labels = {f.key: f.label.lower() for f in scenario.fields}
    intake_only = set(package.get('intake_only_fields', ()))
    paragraphs = []
    for block in package["blocks"]:
        # Intake-only answers may steer the conversation, but they are not
        # factual assertions for the final document.  Never let an old asset
        # reintroduce such a field into an exported body.
        if intake_only & set(PLACEHOLDER.findall(block["text"])):
            continue
        key = block.get("when_field")
        if key:
            stored = fields.get(key, {})
            if stored.get('status') != 'filled': continue
            if block.get('when_values') is not None and stored.get('value') not in block['when_values']: continue
            if block.get('when_value') is not None and stored.get('value') != block['when_value']: continue
        text = block["text"]
        # Classification answers are routing metadata, not a legal assertion.
        # Pinned old templates must obey the same boundary as new templates.
        if '{{procedure}}' in text and fields.get('procedure', {}).get('origin') not in {'verified_rule', 'user_verified'}:
            sentences = re.split(r'(?<=\.)\s+(?=[А-ЯЁ])', text)
            text = ' '.join(s for s in sentences if '{{procedure}}' not in s)
            if not text: continue
        if block.get("role") == "title":
            text = text.replace("о оплате", "об оплате")  # Also correct pinned older sessions.
        def substitute(match):
            value = formatted.get(match[1]) or f"[{labels[match[1]]}]"
            return strip_template_label_echo(value, text[:match.start()])
        if block.get('role')=='place_date' and '{{place}}' in text and '{{date}}' in text:
            text=re.sub(r'\}\}[ \t]+\{\{','}}\t{{',text)
        rendered = PLACEHOLDER.sub(substitute, text)
        rendered = re.sub(r"\.(?:[ \t]*\.)+", ".", rendered)
        rendered = re.sub(r"([.!?])([ \t]+)([а-яё])", lambda m: m[1] + m[2] + m[3].upper(), rendered)
        paragraphs.append({"role": block.get("role", "body"), "text": rendered})
    return paragraphs
