"""Present source checks as service work, never as missing client facts."""
import re

from app.services.document_formula_registry import NEEDS_INPUT, REVIEW_REQUIRED, normalize_calculation_plan, primary_pending_rule


_RETRY_ACTIONS = {
    "load_key_rate_history", "retry_key_rate_history",
    "load_labor_delay_rates", "retry_labor_delay_rates",
}
_REBUILD_ACTION = "rebuild_calculation_plan"


def is_formula_source_retry(message: str) -> bool:
    # Only standalone commands: mixed corrections must first reach fact intake.
    return bool(re.fullmatch(
        r"\s*(?:пожалуйста[, ]+)?(?:повтори(?:те|ть)?(?:\s+проверку(?:\s+(?:источника|ставок|расч[её]та))?)?"
        r"|проверь(?:те)?\s+(?:источник|ставки)\s+(?:ещ[её]\s+раз|снова)"
        r"|попробуй(?:те)?\s+ещ[её]\s+раз)(?:[, ]+пожалуйста)?[.!]?\s*",
        message, re.I,
    ))


def formula_retry_action(state: dict) -> str | None:
    """Return the actionable saved blocker for an explicit retry command."""
    rule = primary_pending_rule(state.get("calculation_plan") or {})
    if not rule or rule.get("status") != REVIEW_REQUIRED:
        return None
    action = str(rule.get("system_action") or "").strip()
    return action or None


def rebuild_formula_plan(state: dict) -> None:
    """Discard only a corrupt plan and rebuild it from persisted user facts."""
    action = formula_retry_action(state)
    if action != _REBUILD_ACTION:
        return
    previous = state.pop("calculation_plan", None)
    requested = [
        str(item.get("id")) for item in (previous or {}).get("rules", ())
        if isinstance(item, dict) and item.get("id")
    ]
    if requested:
        state["formula_requested_rules"] = list(dict.fromkeys([
            *state.get("formula_requested_rules", ()), *requested,
        ]))
    from app.services.document_formula_intake import synchronize_formula_plan
    synchronize_formula_plan(state, force=True, retry_sources=False)


def is_formula_control(message: str) -> bool:
    if is_formula_source_retry(message):
        return True
    return bool(re.fullmatch(
        r"\s*(?:пожалуйста[, ]+)?(?:"
        r"(?:я\s+)?уже\s+(?:отвечал[аи]?|писал[аи]?|сообщал[аи]?|говорил[аи]?)"
        r"|(?:посмотри|смотри|прочитай)\s+выше"
        r"|(?:продолжить|продолжай|продолжим|дальше|далее|что\s+дальше|следующий\s+вопрос)"
        r"|(?:сделай|создай|сформируй|подготовь|пришли|отправь|дай|скачай)(?:те)?"
        r"(?:\s+мне)?\s+(?:файл|документ|черновик|docx|ворд|word)"
        r"|(?:где|когда)\s+(?:(?:мой|моя)\s+)?(?:файл|документ|иск|претензия)"
        r")(?:[, ]+пожалуйста)?[.!?]?\s*", message, re.I,
    ))


def is_incomplete_calculation_draft(message: str) -> bool:
    """An explicit standalone request, never a negation or a question."""
    return bool(re.fullmatch(
        r'\s*(?:пожалуйста[, ]+)?(?:(?:подготовь|сделай|создай|пришли|дай|скачай|сформируй)(?:те)?\s+'
        r'(?:мне\s+)?)?(?:черновик|файл|документ)\s+с\s+(?:незаверш[её]нным|неподтвержд[её]нным)'
        r'\s+расч[её]том(?:[, ]+пожалуйста)?[.!]?\s*', message or '', re.I,
    ))


def incomplete_calculation_notes(state: dict) -> list[str]:
    plan = normalize_calculation_plan(state.get('calculation_plan') or {})
    rules = {rule['id']: rule for rule in plan.get('rules', []) if rule.get('id')}
    notes = []
    for rule in rules.values():
        if rule.get('status') not in {NEEDS_INPUT, REVIEW_REQUIRED}:
            continue
        label = rule['label']
        if rule['id'] == 'civil_395':
            label += ' (статья 395 ГК РФ)'
        dependencies = [rules[k]['label'] for k in rule.get('blocked_by', []) if k in rules]
        if dependencies:
            reason = 'ожидает завершения расчёта «' + '», «'.join(dependencies) + '».'
        elif rule['status'] == NEEDS_INPUT:
            reason = 'для определения суммы требуются дополнительные сведения.'
        else:
            # The source error can include technical or untrusted text.
            from app.services.document_formula_registry import _review_reason
            reason = _review_reason(label, rule.get('system_action'))
        notes.append(f'{label}. Расчёт не завершён. {reason[0].upper()}{reason[1:]}')
    return notes


def pending_input_signature(plan: dict):
    """Keep the unanswered formula input distinct from a later calculation."""
    rule = primary_pending_rule(plan) or {}
    if rule.get('status') == NEEDS_INPUT:
        return [rule.get('id'), rule.get('missing')]
    return None


def hide_unfinished_totals(state: dict, rendered_fields: dict) -> dict:
    """Remove stale derived totals from the export snapshot, preserving primary facts."""
    visible = dict(rendered_fields)
    plan = normalize_calculation_plan(state.get('calculation_plan') or {})
    duty_only = set(plan.get('unresolved_rule_ids') or ()) == {'state_duty'}
    for key, source in state.get('fields', {}).items():
        # The fee uses a separate tariff. It does not change an independently
        # established principal balance or the claim price derived from it.
        if duty_only and key != 'fee' and source.get('origin') in {'loan_arithmetic', 'service_balance_arithmetic'}:
            continue
        if (key not in {'claim_price', 'fee', 'calculation'} and
                source.get('origin') not in {'calculation_plan', 'calculation_plan_composition', 'source_bound_arithmetic'}):
            continue
        value = source.get('formula_base_value')
        if key in {'claim_price', 'fee', 'calculation'} or source.get('formula_base_origin') in {
                'calculation_plan', 'calculation_plan_composition', 'source_bound_arithmetic'}:
            value = None
        visible[key] = {'status': 'filled' if value else 'review_required', 'value': value}
    return visible

def formula_review_message(state: dict) -> str | None:
    rule = primary_pending_rule(state.get("calculation_plan") or {})
    if not rule or rule.get("status") != REVIEW_REQUIRED:
        return None
    reason = str(rule.get("review_reason") or "Требуется проверка основания расчёта со стороны сервиса.").strip()
    label = str(rule.get("label") or "денежного требования")
    answer = f"Расчёт «{label}» пока не завершён. {reason}\n\nУже сообщённые сведения сохранены."
    if rule.get("system_action") in _RETRY_ACTIONS and state.get("official_rate_lookup", True):
        answer += ' Напишите «повтори проверку источника», чтобы сервис снова проверил ставки по сохранённым данным.'
    elif rule.get("system_action") == _REBUILD_ACTION:
        answer += ' Напишите «повтори проверку расчёта», чтобы сервис пересобрал расчёт по сохранённым данным.'
    else:
        answer += " Для завершения нужна проверка расчёта со стороны сервиса; повторять уже сообщённые суммы и даты не нужно."
    answer += ' Чтобы получить рабочий файл до завершения расчёта, напишите «подготовь черновик с незавершённым расчётом».'
    return answer


def pause_for_formula_review(state: dict) -> str | None:
    answer = formula_review_message(state)
    if answer:
        state.update(phase="collecting", last_questions=[], question_origin="calculation_review", question_field=None)
    return answer
