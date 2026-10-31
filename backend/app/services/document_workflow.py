"""Persistent JSON interview. The server decides completeness, never the LLM."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
import logging
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.core.prompts import LEGAL_SCOPE_RULES
from app.services.document_scenarios import SCENARIOS, render_scenario, field_is_active
from app.services.gigachat_client import get_gigachat_client
from app.services.llm_cost import TokenUsage
from app.services.document_dialogue import (
    asks_for_help, leaves_blank, conversational_value, document_kind, infer_scenario,
    classification_guidance, field_guidance, normalize_address, has_locality, question_text, is_progress_message, is_recall_request, scenario_candidates,
)

logger = logging.getLogger(__name__)


def seed_explicit_authority(state):
    """A named authority in the request is not the employer/opposing party."""
    choices = {
        "complaint_labor_agency": (r"трудов\w* инспекц\w*|инспекц\w* (?:по )?труд\w*|роструд", "Государственная инспекция труда", r"инспекц|роструд"),
        "complaint_consumer_agency": (r"роспотребнадзор\w*", "Роспотребнадзор", r"роспотребнадзор"),
    }
    target = choices.get(state.get("scenario"))
    if not target: return
    evidence = re.search(target[0], state.get("request", ""), re.I)
    if not evidence: return
    stored = state.setdefault("fields", {}).get("recipient", {})
    if stored.get("status") == "filled" and re.search(target[2], stored.get("value") or "", re.I): return
    if stored.get("value"): state.setdefault("previous_recipient", deepcopy(stored))
    state["fields"]["recipient"] = {"status": "filled", "value": target[1], "evidence": evidence[0], "origin": "explicit_request_target", "error": None}


def provider_failure_kind(error):
    cause = error
    for _ in range(5):
        name = type(cause).__name__
        if name in {"ConnectTimeout", "ConnectError"}: return "connection"
        if name in {"ReadTimeout", "WriteTimeout", "PoolTimeout"}: return "timeout"
        if getattr(cause, "status_code", None) in {401, 403}: return "authorization"
        if getattr(cause, "status_code", None) in {402, 429}: return "limit"
        if getattr(cause, "status_code", None): return "provider_http"
        if cause.__cause__ is None: break
        cause = cause.__cause__
    return "invalid_response" if isinstance(error, ValueError) or "structured" in str(error) else "provider_unavailable"


class FieldUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    value: str | None = Field(default=None, max_length=12000)
    status: Literal["filled", "unknown", "not_applicable"]
    evidence: str = Field(min_length=1, max_length=12000)


class InterviewReply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    updates: list[FieldUpdate] = Field(default_factory=list, max_length=80)
    explanation: str = Field(default="", max_length=6000)
    intent: Literal["answer", "help", "cancel"] = "answer"


def new_state(prompt: str, *, context="", title="", filename="document-draft", output_format="docx", document_type=""):
    return {"version": 2, "controller_version": 3, "phase": "classifying", "scenario": None, "fields": {},
            "request": prompt, "context": context, "title_hint": title, "document_type_hint": document_type,
            "filename": filename, "output_format": output_format, "last_questions": [], "revision": 0,
            "official_rate_lookup": True}


def normalize_money(raw: str) -> str | None:
    text = raw.lower().strip().replace("\u00a0", " ")
    text=re.sub(r'\s*(?:ежемесячно|в месяц|за месяц)[.! ]*$','',text).strip()
    match = re.fullmatch(r"(\d+(?:[ ]\d{3})*(?:[.,]\d{1,2})?)\s*(тыс\.?|тысяч(?:а|и)?|млн\.?)?\s*(?:руб(?:\.|лей|ля|ль)?|₽)?", text)
    if not match:
        return None
    try:
        number = Decimal(match[1].replace(" ", "").replace(",", "."))
        if match[2]:
            number *= 1000000 if match[2].startswith("млн") else 1000
        if number <= 0 or number > Decimal("1000000000000000"):
            return None
        return format(number.quantize(Decimal("0.01")), "f")
    except InvalidOperation:
        return None


def normalize_field(spec, raw: str) -> tuple[str, str | None]:
    value = raw.strip()
    if not value or re.search(r"\[[^]]+\]", value):
        return value, "Укажите значение либо прямо сообщите, что оно неизвестно."
    if spec.key=='contacts' and spec.label=='Контактные данные':
        from app.services.document_case_facts import normalize_contacts
        contacts=normalize_contacts(value)
        return (contacts,None) if contacts else (value,'Укажите телефон или электронную почту либо сообщите, что не хотите их добавлять. Почтовый адрес хранится отдельно.')
    if spec.kind == 'choice':
        from app.services.document_schema import normalize_choice
        choice = normalize_choice(spec, value)
        return (choice, None) if choice else (value, 'Нужно выбрать один вариант: ' + ', '.join(spec.choices) + '. Какой подходит?')
    if spec.kind == 'duration':
        duration = re.sub(r'^на\s+', '', value, flags=re.I)
        match = re.fullmatch(r'(\d+)\s*(?:год|года|лет|месяц(?:а|ев)?|день|дня|дней|недел[яьиь])', duration, re.I)
        if match and int(match[1]) > 0:
            return duration, None
        return value, 'Укажите срок как продолжительность, например: 2 года или 11 месяцев. Какой срок согласовали стороны?'
    if spec.key == 'requests' and re.search(r'решить (?:вопрос|проблем\w*)|разобраться (?:с|со)\b|сделать что-нибудь', value, re.I):
        return value, 'Нужно уточнить конкретное действие для просительной части. Что именно, помимо денежного возмещения, вы хотите просить у суда? Можно оставить только возмещение ущерба.'
    if spec.kind == "money":
        money = normalize_money(value)
        return (money, None) if money else (value, f"Какую сумму в рублях указываем в поле «{spec.label}»? Например: 7000 рублей. Пример не является вашими данными.")
    if spec.kind == "date":
        value = re.sub(r'^(?:с|со|от|до|на)\s+', '', value, flags=re.I).strip()
        months = {"января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
                  "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12}
        words = re.fullmatch(r"(\d{1,2})\s+([а-я]+)\s+(\d{4})(?:\s*г(?:ода|\.)?)?", value.lower())
        if words and words[2] in months:
            try:
                return datetime(int(words[3]), months[words[2]], int(words[1])).date().isoformat(), None
            except ValueError:
                pass
        for pattern in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d.%m.%y"):
            try:
                return datetime.strptime(value, pattern).date().isoformat(), None
            except ValueError:
                pass
        return value, "Укажите полную дату с годом, например: 25.10.2026. Пример не является вашими данными."
    if spec.kind == "address":
        value = normalize_address(value)
        # A heuristic for completeness, not address verification. Rural/nonstandard
        # addresses need an explicit description of the property, not a made-up street.
        if len(value) < 15 or not re.search(r"\d", value):
            return value, ("Этого недостаточно для полного адреса. Укажите населённый пункт, улицу и дом, корпус/квартиру при наличии, индекс если известен. "
                           "Например: г. Екатеринбург, ул. Примерная, д. 10, кв. 5. Это вымышленный пример. "
                           "Если у адреса нет улицы или номера, опишите его особенности; если адрес неизвестен, так и напишите.")
        if not has_locality(value):
            return value, f"В адресе не указан населённый пункт. Сохранил указанную часть: {value}. Какой город или другой населённый пункт нужно добавить?"
        from app.services.document_addresses import address_error
        return value, address_error(value)
    return value, None


def _evidence_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold().replace("ё", "е")).strip()


def apply_updates(state: dict, updates: list[FieldUpdate], message: str, *, latest_message=None) -> dict:
    result = deepcopy(state)
    scenario = SCENARIOS[result["scenario"]]
    specs = {f.key: f for f in scenario.fields}
    for patch in updates:
        if patch.key not in specs or _evidence_text(patch.evidence) not in _evidence_text(message):
            continue
        from app.services.document_export_contract import ROLE_FIELDS, role_evidence_allowed
        active = result.get('last_questions', [])
        direct = patch.key in active and _evidence_text(patch.evidence) in _evidence_text(latest_message if latest_message is not None else message)
        if patch.key in ROLE_FIELDS and active and not role_evidence_allowed(patch.key, patch.evidence, result, direct=direct):
            continue
        # Never copy values from the question, a prompt example or another client's state.
        if patch.status == "filled":
            if patch.value is None:
                continue
            if specs[patch.key].kind != 'choice' and conversational_value(patch.value):
                continue
            original = patch.value
            if _evidence_text(original) not in _evidence_text(patch.evidence):
                # Preserve the actual narrative instead of accepting the model's
                # paraphrase, which may silently add or omit material facts.
                if patch.key == "facts":
                    original = patch.evidence
                else:
                    continue
            value, error = normalize_field(specs[patch.key], original)
            if patch.key in {"sender", "recipient", "signature", "counterparty_signature"} and re.fullmatch(r"[а-яё-]+(?:\s+[а-яё-]+){1,2}", value) and not re.search(r"\b(?:ооо|ип|ао|пао|зао)\b", value):
                value = value.title()
            if result['fields'].get(patch.key,{}).get('value')!=value:
                from app.services.document_case_facts import invalidate_case_facts
                invalidate_case_facts(result,patch.key)
            result["fields"][patch.key] = {"value": value, "original": original,
                "evidence": patch.evidence, "status": "incomplete" if error else "filled", "error": error}
            if specs[patch.key].kind == 'address':
                from app.services.document_addresses import components, store_reference
                result['fields'][patch.key]['address_components'] = components(value)
                store_reference(result, patch.key, original)
            if direct:
                binding = {'field': patch.key, 'text': patch.evidence}
                if binding not in result.setdefault('answer_bindings', []): result['answer_bindings'].append(binding)
        else:
            # Unknown/inapplicable must be an explicit user decision, not the model's default.
            if not (leaves_blank(patch.evidence) or re.search(r"не знаю|неизвест|не помню|сомнева|позже|самостоятельно|сам[а]? впиш|не примен|не нужно|не требуется|нет\b|отсутств|не было|без прилож", patch.evidence, re.I)):
                continue
            from app.services.document_case_facts import invalidate_case_facts
            invalidate_case_facts(result,patch.key)
            result["fields"][patch.key] = {"value": None, "original": None,
                "evidence": patch.evidence, "status": patch.status, "error": None}
    result["revision"] += 1
    return result


_READY_EDIT_VERB = r"(?:дозаполн\w*|дополн\w*|исправ\w*|измени\w*|замени\w*|добав\w*|укаж\w*)"
_READY_LABELLED_EDIT = re.compile(
    rf"\b{_READY_EDIT_VERB}\s+(?P<label>[^:;\n]{{2,80}}?)\s*[:—–-]\s*"
    # A dot only ends a value when it is a sentence boundary, not when it is
    # part of a date or a decimal amount.
    r"(?P<value>.+?)(?=(?:[;!\n]|\.(?=\s|$)|$))",
    re.IGNORECASE,
)
_READY_LABEL_STOPWORDS = {
    "в", "во", "на", "по", "для", "от", "до", "с", "со", "и", "или",
    "поле", "поля", "значение", "значением", "данные", "данных", "мой", "моё",
}


def _ready_label_tokens(value: str) -> set[str]:
    """Return conservative, human-facing tokens for a post-ready field edit.

    A ready interview has no active field, so a follow-up such as
    ``дозаполни срок исполнения: 2 недели`` needs a small local bridge back
    into the existing schema.  This deliberately uses labels rather than a
    list of scenario names: future template fields receive the same behaviour.
    """
    return {
        token.casefold().replace("ё", "е")
        for token in re.findall(r"[А-Яа-яЁёA-Za-z][А-Яа-яЁёA-Za-z-]*", value or "")
        if len(token) > 1 and token.casefold().replace("ё", "е") not in _READY_LABEL_STOPWORDS
    }


def _ready_labelled_updates(state: dict, message: str) -> list[FieldUpdate]:
    """Extract explicit ``field label: value`` corrections after readiness.

    This is intentionally narrower than free-text fact extraction.  It avoids
    changing a completed document merely because a person asks a general legal
    question, while supporting a natural, template-independent way to correct
    any labelled field.  Values remain literal user evidence and go through
    the usual ``apply_updates`` validation.
    """
    scenario = SCENARIOS.get(state.get("scenario"))
    if not scenario:
        return []
    updates: list[FieldUpdate] = []
    seen: set[str] = set()
    for match in _READY_LABELLED_EDIT.finditer(message or ""):
        label = match.group("label").strip()
        value = match.group("value").strip().rstrip(". ")
        query = _ready_label_tokens(label)
        if not query or not value:
            continue
        candidates: list[tuple[int, object]] = []
        for spec in scenario.fields:
            # Use both a visible label and a stable internal key.  Requiring at
            # least two words (unless the label itself is exact) prevents a
            # vague instruction like "исправь срок" from choosing between two
            # different dates in a template.
            source = f"{spec.label} {spec.key.replace('_', ' ')}"
            tokens = _ready_label_tokens(source)
            overlap = len(query & tokens)
            exact = " ".join(sorted(query)) == " ".join(sorted(_ready_label_tokens(spec.label)))
            if overlap < (1 if exact else min(2, len(query))):
                continue
            # Validation breaks otherwise unavoidable label ties.  For
            # example, a duration belongs to a response term, not a field
            # whose label also starts with "Срок исполнения" but requires a
            # calendar date.
            _, error = normalize_field(spec, value)
            score = overlap * 10 + (30 if exact else 0) + (4 if error is None else 0)
            candidates.append((score, spec))
        if not candidates:
            continue
        candidates.sort(key=lambda item: item[0], reverse=True)
        best_score, best = candidates[0]
        if len(candidates) > 1 and candidates[1][0] == best_score:
            continue
        if best.key in seen:
            continue
        seen.add(best.key)
        updates.append(FieldUpdate(key=best.key, status="filled", value=value, evidence=value))
    return updates


def _ready_formula_field(state: dict) -> str | None:
    """Choose an existing factual calculation slot without inventing one."""
    scenario = SCENARIOS.get(state.get("scenario"))
    if not scenario:
        return None
    available = {field.key for field in scenario.fields}
    plan = state.get("calculation_plan")
    current = plan.get("current_field") if isinstance(plan, dict) else None
    if current in available:
        return current
    for key in (
        "calculation", "additional_claims", "penalty_calculation", "period_payments",
        "costs", "litigation_costs", "requests", "amount", "claim_price", "fee",
    ):
        if key in available:
            return key
    return None


def _ready_formula_explanation(state: dict, changed_fields: set[str]) -> str:
    """Give a short status without rephrasing or guessing a legal rate."""
    notes: list[str] = []
    if changed_fields:
        labels = {field.key: field.label for field in SCENARIOS[state["scenario"]].fields}
        notes.append("Уточнение сохранено: " + ", ".join(labels[key].lower() for key in changed_fields if key in labels) + ".")
    plan = state.get("calculation_plan")
    if isinstance(plan, dict) and plan.get("status") == "calculated":
        notes.append("Расчёт добавлен по сохранённым данным и проверяемой истории ключевой ставки Банка России.")
        from app.services.document_formula_registry import render_calculation_lines
        lines = render_calculation_lines(plan)
        if lines:
            notes.append("Расчёт: " + " ".join(lines))
    return " ".join(notes)


async def _resume_ready_document(state: dict, message: str):
    """Handle a concrete edit/calculation in a completed document interview.

    A ready state normally has no cursor.  Sending a calculation request from
    that state to generic consultation loses the formula pipeline and tempted
    the language model to give an illustrative, unverified rate.  This route
    accepts only explicit labelled edits or a rule recognised by the shared
    formula registry; all other messages retain the normal consultation path.
    """
    updates = _ready_labelled_updates(state, message)
    if updates:
        state = apply_updates(state, updates, message, latest_message=message)
    from app.services.document_formula_registry import detect_requested_rules
    requested = detect_requested_rules(str(state.get("scenario") or ""), message)
    if requested:
        from app.services.document_calculation_ledger import collect_calculation_turn
        current = _ready_formula_field(state)
        calculated = collect_calculation_turn(state, message, current)
        if calculated:
            return state, True, _ready_formula_explanation(state, {item.key for item in updates})
    if updates:
        return state, True, _ready_formula_explanation(state, {item.key for item in updates})
    return state, False, ""


def pending_fields(state: dict):
    return [f for f in SCENARIOS[state["scenario"]].fields
            if field_is_active(f, state['fields'])
            if state["fields"].get(f.key, {}).get("status") not in {"filled", "unknown", "not_applicable", "review_required"}]


def _needs_contextual_fact_capture(scenario, key, message):
    """Return whether one answer can contain facts for several template slots.

    A short answer such as a name, a date or a single amount is cheaper and
    safer to accept locally.  A detailed factual description is different: it
    often gives the contract, performance, deadline and breach in one turn.
    Treating it as the answer to whichever question happened to be on screen
    is what led to repeated questions and duplicated document text.
    """
    if not key or asks_for_help(message) or re.search(r"\b(?:исправь|измени|замени|убери)\b", message, re.I):
        return False
    spec = next((field for field in scenario.fields if field.key == key), None)
    if not spec or spec.kind != "text" or key in {
        "legal_basis", "fee", "jurisdiction", "signature", "counterparty_signature",
        "sender", "recipient", "sender_details", "recipient_details", "party_details",
    }:
        return False
    source = message.strip()
    # Short procedural confirmations (for example, "да, 2.10.26, ответа
    # нет") are intentionally handled by the family-specific local parsers.
    # Sending those to the contextual model would make otherwise offline-safe
    # intake depend on GigaChat and could turn a date confirmation into a new
    # narrative slot.
    if len(source) < 120 and not re.search(
        r"договор\w*|услуг\w*|работ\w*|оплат\w*|долг\w*|задолж\w*|ущерб\w*|не\s+поступ\w*|не\s+вернул\w*|акт\w*",
        source,
        re.I,
    ):
        return False
    if len(source) >= 120:
        return True
    # Multiple independent clauses, dates or money values are strong evidence
    # that a user has answered more than the active slot.
    clauses = len(re.findall(r"[.;]\s+", source))
    dates = len(re.findall(r"\b\d{1,2}(?:[./]\d{1,2}[./]\d{2,4}|\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+\d{4})", source, re.I))
    amounts = len(re.findall(r"\b\d+(?:[ \u00a0]\d{3})*(?:[.,]\d{1,2})?\s*(?:руб(?:лей|ля|ль|\.)?|₽)\b", source, re.I))
    return clauses >= 2 or dates >= 2 or amounts >= 2


async def _capture_contextual_facts(state, scenario, key, message):
    """Extract literal facts from a rich answer before the local fast path.

    The model is allowed to choose *which* currently empty template slots the
    answer covers, but it can only return literal snippets of the latest user
    turn.  This preserves provenance and lets the deterministic field checks
    remain the final gate.  Failure is intentionally local: ordinary intake
    must still work when the provider is temporarily unavailable.
    """
    if not _needs_contextual_fact_capture(scenario, key, message):
        return state, None
    blocked = {
        "legal_basis", "fee", "jurisdiction", "signature", "counterparty_signature",
        "sender", "recipient", "sender_details", "recipient_details", "party_details",
    }
    eligible = [field for field in scenario.fields
                if field.key not in blocked
                and (field.key == key or state.get("fields", {}).get(field.key, {}).get("status")
                     not in {"filled", "unknown", "not_applicable", "review_required"})]
    if len(eligible) < 2:
        return state, None
    keys = [field.key for field in eligible]
    schema = {
        "type": "object",
        "properties": {
            "answers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "enum": keys},
                        "quote": {"type": "string"},
                    },
                    "required": ["key", "quote"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["answers"],
        "additionalProperties": False,
    }
    try:
        completion = await _structured(
            await get_gigachat_client(),
            "Извлеки из latest_message все уже названные факты для полей выбранного шаблона. "
            "Это не опрос и не редактура: верни только короткие дословные непрерывные цитаты из latest_message. "
            "Не придумывай, не перефразируй и не копируй одну цитату в несколько полей. "
            "Договор — только его вид, номер, дату и стороны; исполнение — только выполненная работа или услуга; "
            "срок оплаты — только дата или период оплаты; обстоятельства нарушения — только факт просрочки, отсутствия оплаты или обращений. "
            "Основная задолженность — неоплаченный остаток, а не вся цена договора и не аванс. "
            "Не заполняй срок исполнения претензии датой, установленной для оплаты по договору. "
            "Не извлекай просьбу пользователя рассчитать проценты как денежный факт: её обработает калькулятор.",
            {
                "scenario": scenario.as_dict(),
                "active_field": key,
                "fields": [{"key": field.key, "label": field.label, "kind": field.kind,
                            "question": field.question} for field in eligible],
                "already_filled": state.get("fields", {}),
                "latest_message": message,
            },
            schema,
            name="contextual_template_facts",
            plain_json=True,
        )
        payload = json.loads(completion.content)
        seen = set()
        updates = []
        for item in payload.get("answers", []):
            field_key = item.get("key")
            quote = str(item.get("quote") or "").strip()
            if field_key not in keys or not quote or field_key in seen:
                continue
            if _evidence_text(quote) not in _evidence_text(message):
                continue
            spec = next(field for field in eligible if field.key == field_key)
            value = quote
            if spec.kind == "money" and normalize_money(value) is None:
                money = re.findall(r"\d+(?:[ \u00a0]\d{3})*(?:[.,]\d{1,2})?\s*(?:тыс\.?|тысяч(?:а|и)?|млн\.?)?\s*(?:руб(?:лей|ля|ль|\.)?|₽)", quote, re.I)
                if len(money) == 1:
                    value = money[0]
            seen.add(field_key)
            updates.append(FieldUpdate(key=field_key, status="filled", value=value, evidence=quote))
        if not updates:
            return state, completion.usage
        return apply_updates(state, updates, message, latest_message=message), completion.usage
    except (RuntimeError, ValueError, TypeError, AttributeError, json.JSONDecodeError):
        return state, None


def interview_message(state: dict, explanation="") -> str:
    scenario = SCENARIOS[state["scenario"]]
    pending = pending_fields(state)
    lines = [explanation.strip()] if explanation.strip() else []
    if pending:
        selected = pending[:1]
        state["last_questions"] = [f.key for f in selected]
        state["phase"] = "collecting"
        for i, f in enumerate(selected, 1):
            current = state["fields"].get(f.key, {})
            lines.append(current.get('error') or question_text(state, f))
    else:
        state["phase"] = "ready"
        state["last_questions"] = []
        lines.append('Все поля опроса обработаны. Проверьте собранные сведения; исправления и дополнительные вопросы можно написать следующим сообщением.')
        lines.append("Собранные факты будут изложены официальным языком. Неизвестные реквизиты останутся подписанными полями; перед подачей их нужно дополнить.")
    return "\n\n".join(lines)


async def _structured(client, system, data, schema, *, name="document_interview", description="Структурированный результат опроса", plain_json=False):
    messages = [{"role": "system", "content": LEGAL_SCOPE_RULES + "\n" + system},
                {"role": "user", "content": json.dumps(data, ensure_ascii=False)}]
    if plain_json:
        def shape(spec):
            if spec.get("type") == "object": return {key: shape(value) for key, value in spec.get("properties", {}).items()}
            if spec.get("type") == "boolean": return True
            if spec.get("type") == "array": return []
            return ""
        messages[0]["content"] += ("\nВерни ровно один заполненный JSON-объект без Markdown, вступления или описания схемы. "
            "Не выводи type, properties, required, description. Заполни эту форму значениями по исходным данным: "
            + json.dumps(shape(schema), ensure_ascii=False))
        return await client.chat_completion(messages, model=settings.GIGACHAT_MODEL, temperature=0.1)
    try:
        return await client.chat_completion(messages, model=settings.GIGACHAT_MODEL, temperature=0.0,
            structured_function={"name": name, "description": description, "parameters": _function_schema(schema)})
    except RuntimeError as error:
        if "requested structured function" not in str(error):
            raise
        # Some GigaChat replies omit the function call. Request ordinary JSON
        # once; the caller still validates its exact schema and source evidence.
        return await _structured(client, system, data, schema, name=name, description=description, plain_json=True)


def _function_schema(schema):
    """GigaChat function parameters accept scalar types, not nullable JSON Schema unions.

    Keep the stricter Pydantic schema for validation. On the wire unknown optional
    strings are empty/omitted; unknown field status still has an explicit enum.
    Never relax types into unconstrained model output to repair provider errors.
    """
    if isinstance(schema, list):
        return [_function_schema(value) for value in schema]
    if not isinstance(schema, dict):
        return schema
    result = {key: _function_schema(value) for key, value in schema.items() if key not in {"title", "default"}}
    if "anyOf" in result:
        alternatives = result.pop("anyOf")
        non_null = [item for item in alternatives if item.get("type") != "null"]
        if len(non_null) != 1 or len(non_null) == len(alternatives):
            raise ValueError("Unsupported function schema union")
        result.update(non_null[0])
    if isinstance(result.get("type"), list):
        non_null = [value for value in result["type"] if value != "null"]
        if len(non_null) != 1:
            raise ValueError("Unsupported function schema type")
        result["type"] = non_null[0]
    if "enum" in result:
        result["enum"] = [value for value in result["enum"] if value is not None]
    return result



def sanitize_interview(state):
    """Repair invalid legacy slots without erasing the original conversation."""
    result = deepcopy(state)
    from app.services.document_routing import scenario_has_evidence, scope_text
    if (result.get('scenario') and re.search(r'алимент', scope_text(result), re.I)
            and not scenario_has_evidence(result['scenario'], result)):
        result['previous_scenario'] = result['scenario']
        result['previous_fields'] = deepcopy(result.get('fields',{}))
        result.update(scenario=None, phase='classifying', fields={}, last_questions=[],
            unsupported_subject=True, document_title=None)
        for stale in ('text_package','template_selection','generated_document','draft_fields','draft_cache','draft_digest'):
            result.pop(stale,None)
    # Older classifiers selected housing rent for nonresidential sales and
    # left the conversation in classification/consultation indefinitely.
    exact = infer_scenario({"request": result.get("request", ""),
                            "title_hint": result.get("title_hint", "")}, "")
    if exact and result.get("scenario") not in {None, exact}:
        from app.services.document_source_rag import select_document_template
        result["previous_scenario"] = result["scenario"]
        result["scenario"] = exact
        result["text_package"], result['template_selection'] = select_document_template(SCENARIOS[exact], result.get('request', ''))
        allowed = {f.key for f in SCENARIOS[exact].fields}
        result["previous_fields"] = deepcopy(result.get("fields", {}))
        result["fields"] = {k: v for k, v in result.get("fields", {}).items() if k in allowed}
        if SCENARIOS[exact].family != SCENARIOS[result['previous_scenario']].family:
            # A rent-debt answer is not an agreed term of a future contract.
            # Keep identities only; all original answers remain in the archive.
            result['fields'] = {k: v for k, v in result['fields'].items()
                                if k in {'sender', 'sender_address', 'recipient', 'recipient_address'}}
        result["last_questions"] = []
        # Agency addressee is the authority, not the opposing employer/seller.
        if exact.startswith("complaint_"):
            if exact == "complaint_labor_agency":
                old = result["previous_fields"]
                for new_key, old_key in (("employer", "recipient"), ("employer_address", "recipient_address")):
                    if old.get(old_key, {}).get("status") == "filled":
                        result["fields"][new_key] = deepcopy(old[old_key])
                parts = [old[k]["value"] for k in ("agreement", "facts")
                         if old.get(k, {}).get("status") == "filled" and old[k].get("value")
                         and (k != "agreement" or re.search(r"договор|расписк|работ|период", old[k]["value"], re.I))]
                if parts:
                    result["fields"]["facts"] = {"status": "filled", "value": "\n".join(dict.fromkeys(parts)),
                        "origin": "scenario_migration", "evidence": "\n".join(parts)}
            for key in ("recipient", "recipient_address"):
                result["fields"].pop(key, None)
        result["phase"] = "collecting"
        result["scenario_repaired"] = True
        for key in ("draft_fields", "draft_digest", "draft_error", "generated_document", "draft_cache"):
            result.pop(key, None)
    if result.get("scenario") and result.get("phase") == "classifying":
        result["phase"] = "collecting"
    from app.services.document_question_policy import is_legal_help
    # Legacy-state repair may add a recovered field while inspecting another
    # one, so iterate over a snapshot rather than mutating a live dictionary.
    for key, stored in list(result.get("fields", {}).items()):
        value = stored.get("value")
        if stored.get("status") != "filled" or not value or stored.get("origin") == "verified_rule":
            continue
        spec = next((f for f in SCENARIOS[result['scenario']].fields if f.key == key), None) if result.get('scenario') else None
        if spec and spec.kind == 'choice':
            normalized, error = normalize_field(spec, value)
            # Sanitising an already accepted answer must be observationally
            # neutral.  Writing an ``error: null`` key on every choice made
            # an unrelated help request look like it had changed stored user
            # facts, which also invalidated optimistic UI state comparisons.
            stored.update(value=normalized, status='incomplete' if error else 'filled')
            if error:
                stored['error'] = error
            else:
                stored.pop('error', None)
            continue
        from app.services.document_case_facts import absence_reply
        if key in {'sender_details','recipient_details','party_details'} and absence_reply(value):
            # "Никаких" is a valid answer to an optional set of identifiers;
            # it must never be printed as a document requisite.
            stored.update(status="unknown", value=None, original=stored.get("original") or value, error=None)
        elif key == 'other_participants' and absence_reply(value):
            stored.update(status="not_applicable", value=None, original=stored.get("original") or value, error=None)
        elif key == 'signature' and re.fullmatch(r'\s*мо[йёя][.! ]*', value, re.I):
            sender=result.get('fields',{}).get('sender',{})
            if sender.get('status')=='filled':
                stored.update(status='filled', value=sender['value'], original=stored.get('original') or value, error=None)
        elif (result.get('scenario') == 'claim_debt_loan' and key == 'order_history'
              and re.search(r'\bпретензи\w*|\bобращал(?:ась|ся)?\b|\bответа?\s+не\s+(?:получ|было)', value, re.I)):
            # A pre-trial demand cannot prove that an application for a court
            # order was filed.  Keep the real fact in its own slot and hide the
            # intake-only order history from legacy exports.
            if result['fields'].get('pretrial',{}).get('status') != 'filled':
                result['fields']['pretrial']={"status":"filled","value":value,"original":value,"evidence":value,
                                              "origin":"recovered_pretrial"}
            stored.update(status="not_applicable", value=None, original=stored.get("original") or value, error=None)
        elif leaves_blank(value):
            stored.update(status="unknown", value=None, original=stored.get("original") or value, error=None)
        elif conversational_value(value) or is_legal_help(value):
            stored.update(status="needs_clarification", value=None, original=stored.get("original") or value,
                          error=None)
        elif key.endswith("address"):
            spec = next((f for f in SCENARIOS[result["scenario"]].fields if f.key == key), None)
            if spec:
                normalized, error = normalize_field(spec, value)
                stored.update(value=normalized, status="incomplete" if error else "filled")
                if error:
                    stored['error'] = error
                else:
                    stored.pop('error', None)
                from app.services.document_addresses import store_reference
                if stored.get('origin') != 'confirmed_address_reference':
                    store_reference(result, key, stored.get('original') or value)
                else:
                    ref = stored.get('address_reference', {})
                    if result['fields'].get(ref.get('reference_field'), {}).get('value') != ref.get('reference_value'):
                        stored.update(status='incomplete', error='Адрес, на который вы ссылались, изменился. Какой полный адрес нужно указать?')
    # A named appraiser or estimate confirms a possible source, but it cannot
    # replace the component-by-component calculation required in any form.
    # Apply this to old persisted interviews as well as new turns.
    from app.services.document_calculation_ledger import sanitize_calculation
    sanitize_calculation(result)
    result["version"] = 2
    if result.get("scenario"):
        seed_explicit_authority(result)
        result["document_title"] = SCENARIOS[result["scenario"]].title
        if result["scenario"] in {"complaint_labor_agency", "motion_postpone"} and (result.get("text_package") or {}).get("version", 0) < 2:
            from app.services.document_template_library import load_text_package
            result["text_package"] = load_text_package(SCENARIOS[result["scenario"]])
        from app.services.document_legal_context import prepare_managed_fields
        if result.get('phase')=='ready' or any(result['fields'].get(k,{}).get('value') for k in ('fee','legal_basis','jurisdiction')):prepare_managed_fields(result)
        # Maintain structured schemas in old chats too; new questions cannot
        # vanish merely because an older interview was previously marked ready.
        if SCENARIOS[result['scenario']].version > result.get('schema_version', 1):
            result['schema_version'] = SCENARIOS[result['scenario']].version
            from app.services.document_template_library import load_text_package
            result['text_package'] = load_text_package(SCENARIOS[result['scenario']])
            if pending_fields(result) and result.get('phase') == 'ready':
                result['phase'] = 'collecting'
    return result


def _record_reply(state, answer):
    state.setdefault("conversation", []).append({"role": "assistant", "content": answer})
    state["conversation"] = state["conversation"][-24:]
    return state


async def _consult_interview(state, message, key=None):
    if state.get('scenario')=='complaint_labor_agency' and key=='payment':
        answer=('Речь о том, куда инспекция направит вам ответ после рассмотрения жалобы: на почтовый адрес, электронную почту или в личный кабинет сервиса подачи. '
                'Способ подачи самой жалобы — отдельный вопрос. Как хотите получить ответ?')
        return _record_reply(state,answer),answer,_usage([])
    from app.services.document_legal_context import legal_guidance
    from app.services.rag_context import build_rag_context
    scenario = SCENARIOS.get(state.get("scenario"))
    guide = field_guidance(state, key, scenario) if scenario and key else classification_guidance(state)
    if key in {"principal_details", "agent_details"} and re.search(r"каки|данн|паспорт|реквизит", message, re.I):
        return _record_reply(state, guide), guide, _usage([])
    court_document = bool(scenario and (scenario.key.startswith(("claim_", "appeal_", "motion_"))))
    sources = legal_guidance(state)
    if not court_document and not re.search(r"суд|пошлин|иск", message, re.I):
        sources = [source for source in sources if not re.search(r"333|131|статья 17", source["title"])]
    from app.services.document_source_rag import template_guidance
    data = {"request": state["request"], "scenario": scenario.as_dict() if scenario else None,
            'selected_form': template_guidance(state, message),
            "facts": state.get("fields", {}), "conversation": state.get("conversation", [])[-16:],
            "user_evidence": [state["request"], state.get("context", ""), *state.get("user_turns", [])],
            "current_field": key, "field_explanation": guide, "user_question": message,
            "legal_sources": sources, "retrieved_context": build_rag_context(message) if re.search(r"прав|закон|стать|можно ли|пошлин|суд", message, re.I) else ""}
    if key == "calculation":
        data["calculation_context"] = {"known_base_amount": state.get("fields", {}).get("amount", {}).get("value"),
            "moral_damage_amount": "не выбрана пользователем", "total": "не рассчитан"}
    usage = _usage([])
    try:
        client = await get_gigachat_client()
        completion = await client.chat_completion([
            {"role": "system", "content": LEGAL_SCOPE_RULES + "\nТы юридический помощник в живом разговоре о подготовке документа. "
             "Сначала прямо и содержательно ответь на user_question. Объясни термин, приведи понятные варианты или помоги с расчётом. "
             "Ты поясняешь текущий шаг заполнения документа, не меняя режим работы. Не переходи к другому полю. "
             "Не создавай документ в ответе, не предлагай заполнить его самостоятельно и не обсуждай госпошлину или суд, если это не вопрос пользователя. "
             "Если человек раздражён повтором, признай, что вопрос был непонятен, и объясни его другими словами. "
             "Не задавай вопросов: один следующий вопрос добавит приложение. Не требуй от человека знания статей, "
             "Не выдавай анкету или список сведений для всего документа. Продолжай по одному текущему полю. "
             "Готовый документ создаёт приложение в виде скачиваемого файла. Не составляй документ в этой консультации. "
             "Не утверждай, что приложение не умеет создавать или отправлять файлы. "
             "Каждое предложение начинай с заглавной буквы. "
             "подсудности и госпошлины: помоги разобраться по предоставленным источникам. Не придумывай суд, "
             "размер морального вреда, штрафа или неустойки. Если данных для расчёта нет, объясни, чего не хватает. "
             "Не объявляй любое слово 'не знаю' отказом от помощи. Используй исходную просьбу и известные факты. "
             "known_base_amount — только основная стоимость, моральный вред в неё НЕ включён. Не переиначивай это как общую сумму. "
             "Ответь обычным русским текстом, без JSON, отчёта об уверенности и системных комментариев. "
             "Не записывай свою консультацию в документ. Юридические утверждения обоснуй источником; "
             "если источника нет, объясни общий смысл и границы проверки."},
            {"role": "user", "content": json.dumps(data, ensure_ascii=False)}],
            model=settings.GIGACHAT_MODEL, temperature=0.2)
        answer = completion.content.strip()
        usage = completion.usage
        # Some model versions still return an object despite a plain-text request.
        if answer.startswith("{"):
            try: answer = json.loads(answer).get("explanation", "")
            except (ValueError, AttributeError): answer = ""
        question = next((f.question for f in scenario.fields if f.key == key), "") if scenario else ""
        if (len(answer) < 65 or len(answer) > 1800 or _evidence_text(answer) == _evidence_text(question) or answer.count("?") > 1
                or re.search(r"(?:не могу|невозможно|не входит в мои возможности).{0,100}(?:файл|отправ)|(?:шапка|текст|заключение) претензии", answer, re.I)
                or (not court_document and not re.search(r"суд|пошлин|иск", message, re.I) and re.search(r"госпошлин|333\.\d+", answer, re.I))
                or re.search(r"составьте текст|заполните шаблон|\[(?:укажите|название магазина|сумма покупки)", answer, re.I)
                or len(re.findall(r"(?m)^\s*\d+[.)]\s+", answer)) > 3):
            answer = guide
    except (RuntimeError, ValueError):
        answer = guide
    # The shared formula registry owns legal/regulated calculations.  Keep
    # this legacy moral-damage helper only for a consumer's explicit choice of
    # a moral-damage amount; never let a request for Art. 395, a penalty or
    # another formula jump into an unrelated moral-damage question.
    if (key == "calculation" and re.search(r"морал", message, re.I)
            and not state.get("calculation_plan")):
        state["awaiting_component"] = "moral_damage"
    if scenario and key:
        # The server owns the interview cursor. Explanations always return to
        # that one field, even if the model tried to end or redirect the task.
        answer = re.sub(r"[^.!?\n]*\?", "", answer).strip()
        # Do not fall back to older form wording that asks a person to state a
        # legal conclusion (for example, why they are *entitled* to claim).
        # These prompts are used after a legal-help turn, so they must bring
        # the conversation back to the concrete fact the service needs.
        factual_followups = {
            "property_right": "На каком фактическом основании имущество находится у вас: вы собственник, наниматель или иной владелец? Чем это подтверждается?",
            "responsibility": "Какие известные действия или бездействие другой стороны связаны с ущербом и чем это подтверждается?",
            "calculation": "Какие подтверждённые денежные позиции и суммы уже известны: ущерб, расходы или другие отдельные суммы?",
        }
        followup = (state.get("fields", {}).get(key, {}).get("error")
                    or factual_followups.get(key)
                    or question_text(state, next(f for f in scenario.fields if f.key == key)))
        if state.get("awaiting_component") == "moral_damage":
            followup = "Какую сумму компенсации морального вреда хотите заявить?"
        answer = answer + "\n\n" + followup
        state["phase"] = "collecting"
        state["last_questions"] = [key]
        state["help_field"] = key
    return _record_reply(state, answer), answer, usage


async def _finish_interview(state, usages, explanation=""):
    from app.services.document_form_intake import prepare_form_intake
    prepare_form_intake(state)
    from app.services.document_case_facts import automatic_case_fields
    automatic_case_fields(state)
    # Use the same calculation planner for every form family after each
    # factual answer.  A pending formula becomes one specific factual question
    # instead of a generic consultation or an unpriced document paragraph.
    from app.services.document_formula_intake import synchronize_formula_plan
    synchronize_formula_plan(state)
    from app.services.document_legal_context import prepare_managed_fields
    prepare_managed_fields(state)
    from app.services.document_scenarios import field_is_active
    # Save inactive answers for provenance, but do not send them to the editor
    # or publish stale branches after the user changes the controlling answer.
    state['inactive_fields'] = [f.key for f in SCENARIOS[state['scenario']].fields if not field_is_active(f, state['fields'])]
    answer = interview_message(state, explanation)
    # The artifact service owns editing and delivery. Running the editor here
    # and again in that service doubled requests and discarded partial progress.
    return _record_reply(state, answer), answer, _usage(usages)


async def advance_interview(state: dict, message: str, *, prior_user_turns=None):
    """Keep a failed answer attached to its question and allow an explicit retry."""
    original = message
    # Stored chats from before the source-backed calculator receive the same
    # verified-rate behaviour as new chats on their next interaction.
    state.setdefault("official_rate_lookup", True)
    retry = state.get("pending_answer")
    retry_pattern = r"\s*(?:повтори|повторить|попробуй ещё раз|попробуй еще раз|продолжим)[.!]?\s*"
    retry_requested = bool(re.fullmatch(retry_pattern, message, re.I))
    if not retry and retry_requested and prior_user_turns:
        # Failed replies in older chats only exist in Message history.
        previous = next((turn for turn in reversed(prior_user_turns)
                         if not re.fullmatch(retry_pattern, turn, re.I) and not asks_for_help(turn)), None)
        if previous: retry = {"message": previous}
    if retry and retry_requested:
        message = retry["message"]
    try:
        updated, answer, usage = await _advance_interview(state, message, prior_user_turns=prior_user_turns)
        if not asks_for_help(message):
            updated.pop("pending_answer", None)
        updated.pop("provider_failure", None)
        return updated, answer, usage
    except (RuntimeError, ValueError) as error:
        # The API persists this JSON together with the assistant's reply. No raw
        # provider error or unvalidated model data becomes a document field.
        saved = sanitize_interview(state)
        turns = list(prior_user_turns if prior_user_turns is not None else saved.get("user_turns", []))
        if not turns or turns[-1] != original: turns.append(original)
        saved["user_turns"] = turns
        saved["pending_answer"] = {"message": message, "questions": list(saved.get("last_questions", []))}
        kind = provider_failure_kind(error)
        saved["provider_failure"] = {"kind": kind, "attempts": state.get("provider_failure", {}).get("attempts", 0) + 1}
        logger.warning("Document interview failure: kind=%s scenario=%s fields=%s", kind, saved.get("scenario"), saved.get("last_questions", []))
        saved.setdefault("conversation", []).append({"role": "user", "content": original})
        reason = {"connection": "Не удалось установить соединение с GigaChat.",
                  "timeout": "GigaChat не ответил за отведённое время.",
                  "authorization": "GigaChat отклонил авторизацию сервиса.",
                  "limit": "GigaChat сообщил об ограничении запросов или доступного лимита.",
                  "invalid_response": "GigaChat вернул данные в неподходящем формате.",
                  "provider_http": "Сервис GigaChat вернул ошибку.",
                  "provider_unavailable": "Сервис GigaChat сейчас недоступен."}[kind]
        answer = ("Ваш ответ сохранён. " + reason + " "
                  "Текущий шаг остаётся прежним. Напишите «повтори», чтобы обработать сохранённый ответ без повторного ввода.")
        return _record_reply(saved, answer), answer, _usage([])


async def _advance_interview(state: dict, message: str, *, prior_user_turns=None):
    result = sanitize_interview(state)
    starting = not result.get("scenario")
    # DB history includes replies whose provider call failed before JSON was
    # saved. Prefer it to the older cached list so those facts are not forgotten.
    turns = list(prior_user_turns if prior_user_turns is not None else result.get("user_turns", []))
    if not turns or turns[-1] != message: turns.append(message)
    result["user_turns"] = turns
    result.setdefault("conversation", []).append({"role": "user", "content": message})
    if not result.get('scenario') and result.get('unsupported_subject') and re.search(r'консультац|объясни.{0,30}услов|разобрать.{0,30}услов',message,re.I):
        result['phase']='cancelled'
        answer='Перехожу к консультации по вашей ситуации. Опишите, какие условия или вопросы нужно разобрать; исходное описание сохранено в чате.'
        return _record_reply(result,answer),answer,_usage([])
    if re.fullmatch(r"\s*(?:отмена|отмени(?:ть)?(?: подготовку(?: документа)?)?|прекратить подготовку)[.!]?\s*", message, re.I):
        result["phase"] = "cancelled"
        return result, "Подготовка документа отменена. Можно продолжить обычную консультацию.", _usage([])
    active = result.get("last_questions", [])
    if not active and result.get("scenario") and result.get("phase") != "classifying":
        pending = pending_fields(result)
        if pending:
            active = [pending[0].key]
            result["last_questions"] = active
            result["phase"] = "collecting"
    key = active[0] if len(active) == 1 else None
    # A completed draft deliberately has no active question.  A later concrete
    # correction or formula request must nevertheless remain in the document
    # workflow: otherwise ``рассчитай проценты`` falls through to generic legal
    # consultation and can receive an illustrative (rather than verified)
    # rate.  Only explicit labelled edits and registry-recognised formulas are
    # resumed here; ordinary messages keep the usual consultation behaviour.
    if result.get("scenario") and result.get("phase") == "ready" and not key:
        result, resumed, explanation = await _resume_ready_document(result, message)
        if resumed:
            return await _finish_interview(result, [], explanation)
    if key and result.get('scenario'):
        spec=next((f for f in SCENARIOS[result['scenario']].fields if f.key==key),None)
        if spec and spec.kind=='address':
            from app.services.document_addresses import explicit_component_correction
            corrected=explicit_component_correction(result['fields'].get(key,{}).get('value'),message)
            if corrected:
                result=apply_updates(result,[FieldUpdate(key=key,status='filled',value=corrected,evidence=corrected)],corrected)
                result['fields'][key]['original']=message
                result['fields'][key]['evidence']=message
                return await _finish_interview(result,[])
    if key and result.get('scenario') and not asks_for_help(message):
        from app.services.document_intake_checks import check_identity_turn
        if check_identity_turn(result,message,key):return await _finish_interview(result,[])
    # This works before form-family-specific intake, so a calculated sum is
    # available in every form that contains both an amount and a calculation
    # slot (not only the clause-document templates).
    if key and result.get('scenario') and not re.search(r'\b(?:исправь|замени|убери|измени)\b',message,re.I):
        from app.services.document_calculation_ledger import collect_calculation_turn
        calculated = collect_calculation_turn(result, message, key)
        if calculated:
            # ``collect_calculation_turn`` already persists a formula plan
            # when it handled a legal formula.  Rebuilding it here from only
            # managed facts used to discard the source-bound dates/rates just
            # captured from the user.  Ordinary component arithmetic keeps its
            # own transparent ledger and is reconciled in ``_finish_interview``.
            return await _finish_interview(result, [])
    # A reply such as "ущерб 128500, оценка 7000, сложи сам" contains both
    # facts and a request for arithmetic.  Let the source-bound calculator
    # consume its concrete components before treating the phrase "сложи" as a
    # general consultation.  Other help requests retain the normal path.
    from app.services.document_calculation_ledger import is_calculation_request
    calculation_fact_turn = key in {'amount', 'calculation'} and is_calculation_request(message)
    if key and result.get('scenario') and (not asks_for_help(message) or calculation_fact_turn) and not re.search(r'\b(?:исправь|замени|убери|измени)\b',message,re.I):
        from app.services.document_case_facts import collect_case_turn
        consumed=collect_case_turn(result,message,key)
        from app.services.document_form_intake import collect_form_turn
        consumed.update(collect_form_turn(result,message,key))
        if consumed:
            # A specialised parser sometimes recognises only the current
            # field in a long narrative.  Let the template-aware extractor
            # inspect the remaining explicit facts before ending that turn.
            # When two or more fields were already captured, the local
            # grammar has done the split and no extra provider call is useful.
            if len(consumed) < 2:
                prior_revision = result.get('revision', 0)
                result, contextual_usage = await _capture_contextual_facts(result, SCENARIOS[result['scenario']], key, message)
                if result.get('revision', 0) != prior_revision:
                    from app.services.document_calculation_ledger import collect_calculation_turn
                    collect_calculation_turn(result, message, key)
                    return await _finish_interview(result, [contextual_usage] if contextual_usage else [])
            return await _finish_interview(result,[])
    if key and result.get('scenario'):
        # Deterministic collectors handle ordinary scalar and well-known
        # narrative forms without a provider call.  Only an unrecognised rich
        # answer reaches the contextual extractor; this keeps explicit local
        # replies offline-safe while still allowing future templates to use
        # GigaChat for multi-field answers.
        prior_revision = result.get('revision', 0)
        result, contextual_usage = await _capture_contextual_facts(result, SCENARIOS[result['scenario']], key, message)
        if result.get('revision', 0) != prior_revision:
            from app.services.document_calculation_ledger import collect_calculation_turn
            collect_calculation_turn(result, message, key)
            return await _finish_interview(result, [contextual_usage] if contextual_usage else [])
    if key and result.get('scenario'):
        spec = next((f for f in SCENARIOS[result['scenario']].fields if f.key == key), None)
        if spec and spec.kind == 'address':
            from app.services.document_addresses import confirm_reference
            if confirm_reference(result, key, message):
                return await _finish_interview(result, [])
        if spec and spec.kind == 'choice' and not asks_for_help(message) and not leaves_blank(message):
            result = apply_updates(result, [FieldUpdate(key=key, status='filled', value=message, evidence=message)], message)
            return await _finish_interview(result, [])
    recall = is_recall_request(message)
    if (is_progress_message(message) or recall) and result.get("scenario"):
        # Acknowledgements are control input, never document data or a reason
        # to start a general legal consultation. Recover legacy missed answers
        # once; current factual replies advance locally below.
        usages = []
        if (recall or (result.get("controller_version", 2) < 3 and not result.get("help_field"))) and pending_fields(result):
            try:
                result, usage = await recover_interview_facts(result)
                usages.append(usage)
                result["progress_recovered"] = True
                result["controller_version"] = 3
            except (RuntimeError, ValueError):
                pass
        return await _finish_interview(result, usages)
    file_intent = file_request_kind(message)
    if file_intent and result.get("scenario"):
        usages = []
        if pending_fields(result):
            result, usage = await recover_interview_facts(result)
            usages.append(usage)
        if file_intent == "create":
            # An explicit request for the file allows a draft with labelled gaps,
            # never invented values. Ordinary answers/help do not skip intake.
            for spec in pending_fields(result):
                result["fields"][spec.key] = {"status": "unknown", "value": None,
                    "evidence": message, "origin": "requested_draft", "error": None}
            result["revision"] += 1
        return await _finish_interview(result, usages)
    semantic_help = key == "requests" and "извинени" in message.lower()
    if (asks_for_help(message) or semantic_help) and not (not result.get('scenario') and infer_scenario(result,message)):
        return await _consult_interview(result, message, key)
    if len(active) > 1 and leaves_blank(message):
        return state, "Уточните, к какому из вопросов относится этот ответ. После этого продолжим по одному полю.", _usage([])
    usages = []
    if not result.get("scenario"):
        result["document_kind"] = document_kind(result)
        if result["document_kind"] == "complaint" and re.search(r"товар|потребител|годност|продукт", result["request"], re.I):
            if re.search(r"роспотребнадзор", message, re.I):
                result["scenario"] = "complaint_consumer_agency"
            elif re.search(r"продавц|магазин|претензи", message, re.I):
                result["document_kind"] = "pretense"
            else:
                answer = "Продавцу направляют требование об устранении нарушения, а в Роспотребнадзор — жалобу для рассмотрения ведомством. Кому вы хотите направить документ: продавцу или в Роспотребнадзор?"
                return _record_reply(result, answer), answer, _usage([])
        choice = infer_scenario(result, message)
        if result.get("scenario"):
            choice = result["scenario"]
        from app.services.document_routing import scope_text, unavailable_form_message
        from app.services.document_catalog import catalog_clarification
        clarification=catalog_clarification(result) if not choice else None
        if clarification:
            result.pop('unsupported_subject',None)
            return _record_reply(result,clarification),clarification,_usage(usages)
        if not choice and result.get('unsupported_subject'):
            result['unsupported_subject'] = True
            answer = unavailable_form_message(result)
            return _record_reply(result, answer), answer, _usage(usages)
        description = re.sub(r"претензи\w*|исков\w*|\bиск\b|взыскан\w*|задолжен\w*|долг\w*|руб\w*|тыс\w*|\d+|\b(?:о|об|на|в|по|с|за|и|мне|нужен|нужна|составь|нужно)\b", " ", message.lower())
        if not choice and result["document_kind"] in {"claim", "pretense"} and len(description.split()) < 3:
            # Type is already known. Ask about the transaction, never ask again
            # whether an explicitly requested pretense is a claim or a pretense.
            answer = classification_guidance(result)
            return _record_reply(result, answer), answer, _usage([])
        if not choice:
            if result['document_kind'] in {'contract', 'act', 'receipt', 'authority', 'appeal'}:
                attempts=result.get('classification_questions',0)
                result['classification_questions']=attempts+1
                if attempts or re.search(r'дарени|брачн|(?:продаж|поставк).{0,25}(?:автомобил|земл|товар)',scope_text(result),re.I):
                    result['unsupported_subject']=True
                    answer=unavailable_form_message(result)
                    return _record_reply(result,answer),answer,_usage(usages)
                answer = classification_guidance(result)
                return _record_reply(result, answer), answer, _usage(usages)
            candidates = scenario_candidates(result)
            client = await get_gigachat_client()
            classification = await _structured(client,
                "Выбери сценарий по фактам и всем ответам. Не запрашивай уже известный вид документа повторно. "
                "Если недостаточно сведений об основании, верни unresolved. Не подменяй неподдерживаемый документ ближайшим.",
                {"request": result["request"], "context": result["context"], "answers": turns,
                 "title_hint": result.get("title_hint", ""), "type_hint": result.get("document_type_hint", ""),
                 "catalog": [{"key": k, "title": SCENARIOS[k].title} for k in candidates]},
                {"type": "object", "properties": {"scenario": {"type": "string", "enum": candidates + ["unresolved"]},
                 "question": {"type": "string"}}, "required": ["scenario", "question"], "additionalProperties": False})
            usages.append(classification.usage)
            choice = json.loads(classification.content).get("scenario")
            if choice not in candidates: choice = "unresolved"
            from app.services.document_routing import scenario_has_evidence
            if choice != 'unresolved' and not scenario_has_evidence(choice, result):
                choice = 'unresolved'
                result['unsupported_subject'] = True
        if choice not in SCENARIOS:
            from app.services.document_routing import unavailable_form_message
            answer = unavailable_form_message(result) if result.get('unsupported_subject') else classification_guidance(result)
            return _record_reply(result, answer), answer, _usage(usages)
        from app.services.document_catalog import is_catalog_form
        if starting and not is_catalog_form(choice):
            result['unsupported_subject']=True
            answer=unavailable_form_message(result)
            return _record_reply(result,answer),answer,_usage(usages)
        result["scenario"] = choice
        result.pop('unsupported_subject', None)
        result["document_title"] = SCENARIOS[choice].title
        from app.services.document_template_library import load_text_package
        from app.services.document_source_rag import select_document_template
        result['text_package'], result['template_selection'] = select_document_template(SCENARIOS[choice], result['request'])
        seed_explicit_authority(result)
    scenario = SCENARIOS[result["scenario"]]
    specs = {f.key: f for f in scenario.fields}
    if starting:
        from app.services.document_case_facts import collect_case_turn
        collect_case_turn(result,message,None)
        from app.services.document_form_intake import collect_form_turn
        collect_form_turn(result,message,None)
    if key in specs and specs[key].kind == 'address':
        from app.services.document_addresses import confirm_reference
        if confirm_reference(result, key, message):
            return await _finish_interview(result, usages)
    if "amount" in specs and not result["fields"].get("amount") and not {'agreement','payments'} <= set(specs):
        amounts = re.findall(r"\b\d+(?:[ ]\d{3})*(?:[.,]\d{1,2})?\s*(?:тыс\.?|тысяч(?:а|и)?|млн\.?)?\s*(?:руб(?:\.|лей|ля|ль)?|₽)", result["request"], re.I)
        if len(amounts) == 1:
            result = apply_updates(result, [FieldUpdate(key="amount", status="filled", value=amounts[0], evidence=amounts[0])], result["request"])
    # An unambiguous short request can start intake locally. More detailed
    # initial descriptions still go through extraction to retain extra facts.
    if starting and len(message) < 180 and not re.search(r"\b[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\b|\d{1,2}[./]\d{1,2}[./]\d{2,4}", message):
        return await _finish_interview(result, usages)
    correction = bool(re.search(r"\b(?:исправь|измени|замени|добавь|убери)\b", message, re.I))
    if key and leaves_blank(message):
        partial = result["fields"].get(key, {})
        if key == "agreement" and partial.get("status") == "incomplete" and "году" in partial.get("error", ""):
            partial.update(status="filled", value=partial["value"] + " [год составления]", error=None,
                           unknown_parts=["year"], year_evidence=message)
            return await _finish_interview(result, usages)
        result = apply_updates(result, [FieldUpdate(key=key, status="unknown", evidence=message)], message)
        return await _finish_interview(result, usages)
    if key in specs and specs[key].optional and re.fullmatch(r'\s*(?:нет|не нужно|отсутствуют)[\\.!\s]*', message, re.I):
        result = apply_updates(result, [FieldUpdate(key=key, status='not_applicable', evidence=message)], message)
        return await _finish_interview(result, usages)
    if key and result.get("awaiting_component") == "moral_damage" and not result.get("calculation_plan"):
        moral = normalize_money(message)
        cost = result["fields"].get("amount", {}).get("value")
        if moral and cost:
            total = Decimal(cost) + Decimal(moral)
            calculation = f"Стоимость товара — {Decimal(cost):.2f} рублей; компенсация морального вреда — {Decimal(moral):.2f} рублей. Общая сумма указанных требований — {total:.2f} рублей."
            result["fields"]["calculation"] = {"status": "filled", "value": calculation, "original": message,
                "evidence": message, "origin": "arithmetic", "components": {"cost": cost, "moral_damage": moral}, "error": None}
            result.pop("awaiting_component", None)
            result["revision"] += 1
            return await _finish_interview(result, usages, "Сложил стоимость товара и выбранную вами компенсацию. Штрафы и неустойку без проверки не добавляю.")
    scalar_answer = key in specs and (
        (specs[key].kind == "money" and (normalize_money(message) is not None or re.fullmatch(r"[\d\s.,₽-]+", message)))
        or (specs[key].kind == "date" and not conversational_value(message))
        or specs[key].kind in {'choice', 'duration'}
        or (specs[key].kind == "address" and not re.search(r"сумм|руб|тыс|исправь|замени|дату", message, re.I)))
    if key and not correction and scalar_answer:
        raw = message
        stored = result["fields"].get(key, {})
        if specs[key].kind == "address" and stored.get("status") == "incomplete" and stored.get('value') and not has_locality(stored.get("value", "")):
            if re.fullmatch(r"(?:г\.?\s*)?[А-Яа-яЁё-]+(?:\s+[А-Яа-яЁё-]+)?", message.strip()):
                raw = "г. " + re.sub(r"^г\.?\s*", "", message.strip(), flags=re.I).title() + ", " + stored["value"]
        patch = FieldUpdate(key=key, status="filled", value=raw, evidence=raw)
        result = apply_updates(result, [patch], raw)
        return await _finish_interview(result, usages)
    if not correction and key in {"sender", "recipient", "signature", "counterparty_signature"} and re.fullmatch(r"[А-Яа-яЁё-]+(?:\s+[А-Яа-яЁё-]+){1,2}[.]?", message.strip()):
        result = apply_updates(result, [FieldUpdate(key=key, status="filled", value=message.strip(), evidence=message)], message)
        return await _finish_interview(result, usages)
    if (not correction and key in {'sender','recipient'} and re.match(r'^(?:ООО|АО|ПАО|ЗАО|ОАО|ИП)\s+\S',message.strip(),re.I)
            and not conversational_value(message)):
        result=apply_updates(result,[FieldUpdate(key=key,status='filled',value=message.strip(),evidence=message)],message)
        return await _finish_interview(result,usages)
    amount_only = normalize_money(message)
    if key and key != "amount" and "amount" in specs and amount_only and not correction:
        result = apply_updates(result, [FieldUpdate(key="amount", status="filled", value=message, evidence=message)], message)
        return await _finish_interview(result, usages, "Сумма сохранена. Продолжим с недостающими сведениями.")
    # Literal answers to a single factual question do not require a model to
    # repeat/classify them. Consultation and corrections retain the AI path;
    # official editing and its fact checks remain separate from raw collection.
    # Every factual text field follows the same contract, including newly
    # added scenarios. There is no incomplete whitelist which can accidentally
    # send a category, purpose or date explanation to general consultation.
    local_fields = {f.key for f in scenario.fields if f.kind == "text"} - {
        "legal_basis", "fee", "jurisdiction", "sender", "recipient", "signature", "counterparty_signature"}
    if (key in local_fields and not correction and not conversational_value(message) and len(message.strip()) >= 3
            and not re.match(r"\s*(?:составь|составить|продолжим|повтори|скача[йт]|забудь|игнорируй)\b", message, re.I)):
        raw = message.strip()
        # A reply about the year can supplement a failed earlier receipt answer
        # without copying assistant examples or inventing a missing date.
        if key == "agreement" and re.match(r"\s*\d{4}\s*(?:год|г\.)", raw, re.I):
            previous = result["fields"].get(key, {}).get("value") or next((turn for turn in reversed(turns[:-1]) if turn != result["request"]
                             and not asks_for_help(turn) and re.search(r"расписк|договор\s+займа", turn, re.I)
                             and re.search(r"\d{1,2}\s+(?:январ|феврал|март|апрел|мая|июн|июл|август|сентябр|октябр|ноябр|декабр)|\d{1,2}[./]\d{1,2}", turn, re.I)), None)
            if previous: raw = previous.strip() + "\nУточнение пользователя: " + raw
        result = apply_updates(result, [FieldUpdate(key=key, status="filled", value=raw, evidence=raw)], raw)
        if "amount" in specs and result["fields"].get("amount", {}).get("status") not in {"filled", "unknown", "not_applicable"}:
            stated_amounts = re.findall(r"\b\d+(?:[ ]\d{3})*(?:[.,]\d{1,2})?\s*(?:тыс\.?|тысяч(?:а|и)?|млн\.?)?\s*(?:руб(?:\.|лей|ля|ль)?|₽)", raw, re.I)
            if (len(stated_amounts) == 1 and key in {"purchase", "service", "goods", "performance", "agreement", "transfer"}
                    and not {'agreement','payments'} <= set(specs)):
                amount = stated_amounts[0]
                result = apply_updates(result, [FieldUpdate(key="amount", status="filled", value=amount, evidence=amount)], raw)
        if (key == "agreement" and "loan" in scenario.key and re.search(r"\d{1,2}\s+(?:январ|феврал|март|апрел|мая|июн|июл|август|сентябр|октябр|ноябр|декабр)|\d{1,2}[./]\d{1,2}", raw, re.I)
                and not re.search(r"\b(?:19|20)\d{2}\b", raw)):
            result["fields"][key].update(status="incomplete", error="В каком году составлена расписка или заключён договор?")
        return await _finish_interview(result, usages)
    # A direct answer about one authority field needs no network classification.
    # It remains an original fact; drafting and legal form checks happen later.
    if (scenario.key == "power_of_attorney" and not correction and not conversational_value(message)
            and (key in {"principal_details", "agent_details"}
                 or (key == "validity" and re.fullmatch(r"\s*\d+\s*(?:год|года|лет|месяц\w*|дн\w*|недел\w*)[.]?\s*", message, re.I))
                 or (key == "powers" and re.search(r"ухаж|уход|забот|представ|получ|забира|подпис|пода[вт]|сопровожд", message, re.I)))):
        result = apply_updates(result, [FieldUpdate(key=key, status="filled", value=message.strip(), evidence=message)], message)
        return await _finish_interview(result, usages)
    client = await get_gigachat_client()
    schema = InterviewReply.model_json_schema()
    schema["properties"]["updates"]["items"] = FieldUpdate.model_json_schema()
    schema["properties"]["updates"]["items"]["properties"]["key"]["enum"] = list(specs)
    schema["required"] = ["updates", "explanation", "intent"]
    schema.pop("$defs", None)
    evidence_input = "\n".join((result["request"], result["context"], *turns))
    completion = await _structured(client,
        "Ты извлекаешь факты из живого разговора о документе. Верни updates, intent и explanation. "
        "Вопрос, просьба пояснить, назвать варианты, выбрать закон или рассчитать сумму — intent=help; не записывай их в поля. "
        "При ответе извлеки все сообщённые факты, в том числе пропущенные раньше. evidence — буквальная цитата, "
        "а value — дословная часть этой цитаты, не слово 'message' и не пересказ. Официальный стиль создаст отдельный редактор. "
        "Текущий вопрос и его смысл даны в active_question. 'Чек о покупке' не является уплатой госпошлины. "
        "'Не определилась' не является названием суда. 'Никому' в вопросе об отправке означает отсутствие отправки. "
        "Не заполняй другие поля на основании предположений. Не перезаписывай ранее заполненные поля, если в latest_message "
        "нет явного исправления. explanation — короткий ответ/уточнение без новых анкетных вопросов. "
        "Не придумывай нормы, даты, имена или суммы. unknown — только при явном отказе от заполнения соответствующего поля.",
        {"scenario": scenario.as_dict(), "current_fields": result["fields"], "last_questions": active,
         "active_question": specs[key].question if key in specs else None,
         "latest_message": message, "user_evidence": evidence_input}, schema)
    usages.append(completion.usage)
    reply = InterviewReply.model_validate_json(completion.content)
    if reply.intent == "help" and not reply.updates:
        if starting:
            # A plain request to create a document is sometimes labelled 'help'
            # by GigaChat. Once its scenario is selected, begin intake instead
            # of returning a general overview of the entire document.
            return await _finish_interview(result, usages)
        result, answer, usage = await _consult_interview(result, message, key)
        return result, answer, _usage(usages + [usage])
    if reply.intent == "cancel":
        # Only the explicit user command handled above may leave intake.
        # A model intent guess cannot silently turn a document chat into advice.
        return await _finish_interview(result, usages)
    before = facts_digest_for_interview(result)
    updates = [patch for patch in reply.updates
               if result["fields"].get(patch.key, {}).get("status") not in {"filled", "unknown", "not_applicable"}
               or _evidence_text(patch.evidence) in _evidence_text(message)]
    result = apply_updates(result, updates, evidence_input, latest_message=message)
    # The model has explicitly classified this as a factual answer. Preserve a
    # single narrative reply if its extraction omitted evidence, never a command.
    if not correction and not any(patch.key != key for patch in updates) and key in specs and specs[key].kind == "text" and key not in {"legal_basis", "fee", "jurisdiction"}:
        if result["fields"].get(key, {}).get("status") not in {"filled", "unknown", "not_applicable"} and not conversational_value(message):
            result = apply_updates(result, [FieldUpdate(key=key, status="filled", value=message.strip(), evidence=message)], message)
    if "amount" in specs and "amount" not in result["fields"]:
        amounts = re.findall(r"\b\d+(?:[ ]\d{3})*(?:[.,]\d{1,2})?\s*(?:тыс\.?|тысяч(?:а|и)?|млн\.?)?\s*(?:руб(?:\.|лей|ля|ль)?|₽)", result["request"], re.I)
        if len(amounts) == 1:
            result = apply_updates(result, [FieldUpdate(key="amount", status="filled", value=amounts[0], evidence=amounts[0])], result["request"])
    if key and before == facts_digest_for_interview(result):
        result, answer, usage = await _consult_interview(result, message, key)
        return result, answer, _usage(usages + [usage])
    # Extraction is data-only. Its free-form explanation can contain another
    # questionnaire; the server alone chooses the next single intake question.
    return await _finish_interview(result, usages)


def facts_digest_for_interview(state):
    from app.services.document_drafting import facts_digest
    return facts_digest(state["fields"])


def file_request_kind(message):
    text = message.lower().strip()
    if not re.search(r"\bфайл\w*|окончательн\w* документ\w*|скачать документ", text):
        return None
    if re.search(r"\bне\s+(?:отправ|присыл|создав|формир|готов)", text):
        return None
    if re.search(r"\b(?:отправь(?:те)?|отправить|пришли(?:те)?|прислать|сформируй(?:те)?|создай(?:те)?|создать|подготовь(?:те)?|подготовить|собери(?:те)?|сделай(?:те)?|скачать|скачай(?:те)?)\b|нужен файл|хочу файл|дай файл", text):
        return "create"
    if re.search(r"где|когда|получ", text):
        return "status"
    return None


async def recover_interview_facts(state):
    """Recover missed answers from user history; assistant examples are excluded."""
    scenario = SCENARIOS[state["scenario"]]
    missing = {f.key for f in pending_fields(state)} | {
        key for key, value in state["fields"].items() if value.get("origin") == "requested_draft"}
    sources = [state["request"], state.get("context", ""), *state.get("user_turns", [])]
    schema = {"type": "object", "properties": {"updates": {"type": "array", "items": {
        "type": "object", "properties": {"key": {"type": "string", "enum": sorted(missing)},
            "source_turns": {"type": "array", "items": {"type": "integer"}}},
        "required": ["key", "source_turns"], "additionalProperties": False}}},
              "required": ["updates"], "additionalProperties": False}
    completion = await _structured(await get_gigachat_client(),
        "Восстанови пропущенные факты из реплик пользователя для документа. Не консультируй и не создавай текст документа. "
        "Для каждого недостающего поля укажи source_turns: номера реплик, в которых пользователь сообщил соответствующий факт. "
        "Одна реплика может сообщать факты для нескольких полей. Не возвращай собственный текст или значения полей. "
        "Не связывай сумму с датой, имя с подписью, срок возврата займа со сроком ответа на претензию. "
        "Вопросы, команды и просьбы о файле не являются данными документа. Не додумывай отсутствующие факты. "
        "Не заполняй поля на основании примеров. Не отмечай неизвестным то, про что пользователь не сообщил явно.",
        {"scenario": scenario.as_dict(), "missing_fields": sorted(missing),
         "user_turns": [{"id": i, "text": value} for i, value in enumerate(sources) if value]}, schema)
    payload = json.loads(completion.content)
    if not isinstance(payload, dict) or not isinstance(payload.get("updates"), list):
        raise ValueError("Invalid recovery response")
    patches = payload["updates"]
    result = deepcopy(state)
    specs = {f.key: f for f in scenario.fields}
    for patch in patches:
        if not isinstance(patch, dict):
            raise ValueError("Invalid recovery update")
        key, ids = patch.get("key"), patch.get("source_turns", [])
        if not isinstance(key, str) or key not in missing or not isinstance(ids, list) or not ids or not all(type(i) is int and 0 <= i < len(sources) for i in ids):
            continue
        selected = [sources[i] for i in dict.fromkeys(ids)]
        if any(not s or asks_for_help(s) or conversational_value(s) or leaves_blank(s) or file_request_kind(s) for s in selected):
            continue
        source = "\n".join(selected)
        from app.services.document_export_contract import role_evidence_allowed
        if not role_evidence_allowed(key, source, result):
            continue
        value = source
        if key in {"signature", "counterparty_signature"} and not (
            re.fullmatch(r"[А-ЯЁа-яё-]+(?:\s+[А-ЯЁа-яё-]+){2}", source.strip()) or re.search(r"подпис", source, re.I)
        ):
            continue
        if key == "due_date" and re.search(r"претензи|срок.{0,15}ответ|исполнени.{0,20}требован", source, re.I):
            # A mixed answer needs the exact contract deadline, never the date
            # selected for responding to this new demand.
            contract_part = re.split(r"[.!?]\s+|\bно\b|\bпоэтому\b", source, flags=re.I)
            source = next((s for s in contract_part if re.search(r"по расписке|по договору", s, re.I)
                           and re.search(r"возврат|верну", s, re.I)), "")
            if not source:
                continue
            value = source
        if specs[key].kind in {"date", "money"}:
            pattern = (r"\b(?:\d{1,2}[./]\d{1,2}[./]\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2}\s+[а-я]+\s+\d{4})\b"
                       if specs[key].kind == "date" else r"\b\d+(?:[ ]\d{3})*(?:[.,]\d{1,2})?\s*(?:тыс\.?|тысяч(?:а|и)?|млн\.?)?\s*(?:руб(?:\.|лей|ля|ль)?|₽)")
            candidates = re.findall(pattern, source, re.I)
            if len(set(candidates)) != 1:
                continue
            value = candidates[0]
        result = apply_updates(result, [FieldUpdate(key=key, status="filled", value=value, evidence=source)], source)
        if result["fields"].get(key, {}).get("status") == "filled":
            result["fields"][key]["origin"] = "recovered_user_turns"
    return result, completion.usage


def _usage(items):
    return TokenUsage(sum(x.prompt_tokens for x in items), sum(x.completion_tokens for x in items),
                      sum(x.total_tokens for x in items), any(x.usage_estimated for x in items))
