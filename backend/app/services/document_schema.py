"""Shared intake/asset contracts and an honest draft-completeness report.

These checks validate structure and facts, not a lawyer's assessment of a case.
"""
import re
from app.services.document_scenarios import SCENARIOS, field_is_active


def normalize_choice(spec, raw):
    text = raw.strip().lower().rstrip('.!')
    if text in spec.choices:
        return text
    if spec.key=='term_type' and re.fullmatch(r'(?:на )?неопредел[её]нн\w*(?: срок)?|бессрочн\w*',text):return 'на неопределённый срок'
    if spec.key=='employment_type':
        if text in {'основная','основной','основное место работы','по основному месту работы'}:return 'основная работа'
        if text in {'по совместительству','совместитель'}:return 'совместительство'
    if spec.key == 'interest_type':
        if text in {'без процентов', 'беспроцентный заём', 'беспроцентный заем'}: return 'беспроцентный'
        if text in {'с процентами', 'процентный заём', 'процентный заем'}: return 'процентный'
    if set(spec.choices) == {'да', 'нет'}:
        if re.fullmatch(r'да|нужно|нужна|хочу|включить|включите', text): return 'да'
        if re.fullmatch(r'нет|не нужно|не нужна|не хочу|не включать', text): return 'нет'
    if spec.key == 'restoration':
        if re.search(r'частич|не полност', text): return 'частично восстановлено'
        if re.search(r'не (?:выполн|сделан|устран|восстанов)|ещ[её] нет|ремонта не было|не ремонт', text): return 'не восстановлено'
        if re.fullmatch(r'(?:ремонт )?(?:сделан|выполнен)|вс[её] (?:устранено|восстановлено)|да', text): return 'восстановлено'
    if spec.key == 'copy_status':
        if re.fullmatch(r'нет(?: ещ[её])?|ещ[её] нет|предстоит|отправка (?:ещ[её] )?предстоит|не (?:отправлены|направлены|отправлял[аи]?|направлял[аи]?)', text): return 'не направлены'
        if re.fullmatch(r'да|(?:уже )?(?:отправлены|направлены|отправил[аи]?|направил[аи]?)', text): return 'направлены'
    return None


def schema_issues(scenario, package):
    """Used at package load and in catalog audit, before any LLM call."""
    issues = []
    specs = {f.key: f for f in scenario.fields}
    for spec in scenario.fields:
        if spec.when_field and (spec.when_field not in specs or not spec.when_values):
            issues.append('invalid_dependency:' + spec.key)
        if spec.when_field and spec.when_field in specs:
            parent = specs[spec.when_field]
            if not set(spec.when_values) <= set(parent.choices): issues.append('invalid_branch:' + spec.key)
        if spec.kind == 'choice' and not spec.choices: issues.append('missing_choices:' + spec.key)
    if package.get('coverage') == 'structured':
        used = set(re.findall(r'\{\{([a-z_]+)\}\}', '\n'.join(b['text'] for b in package['blocks'])))
        # Choice selectors, routing metadata and legally managed jurisdiction
        # are not prose. Every other active question must reach the artifact.
        for spec in scenario.fields:
            if spec.kind != 'choice' and spec.key not in {'procedure', 'jurisdiction'} and spec.key not in used and spec.key not in package.get('intake_only_fields',[]):
                issues.append('unrendered_field:' + spec.key)
    return issues


FORMULA_EXPORT_FIELDS = ("calculation", "claim_price", "fee")

_FORMULA_FIELD_QUESTIONS = {
    "calculation": (
        "Для подготовки файла нужен завершённый расчёт денежных требований. "
        "Укажите составляющие сумм либо недостающие данные для расчёта."
    ),
    "claim_price": (
        "Для подготовки файла нужно определить цену иска по подтверждённым требованиям. "
        "Укажите недостающие суммы либо подтвердите, что дополнительные начисления не заявляются."
    ),
    "fee": (
        "Для подготовки файла нужно определить государственную пошлину или основание освобождения от неё. "
        "Укажите недостающие сведения для расчёта либо подтверждение оплаты или льготы."
    ),
}


def _formula_field_is_rendered(package, key):
    """Whether a formula field can create a visible gap in this artifact."""
    if not package:
        # The generic fallback prints every active scenario field.
        return True
    if key in set(package.get("intake_only_fields", ())):
        return False
    marker = "{{" + key + "}}"
    return any(marker in block.get("text", "") for block in package.get("blocks", ()))


def _plan_issue_field(plan, scenario):
    """Choose an actual interview field for a pending formula plan."""
    available = {spec.key for spec in scenario.fields}
    unresolved = set(plan.get("unresolved_rule_ids") or ())
    for rule in plan.get("rules") or ():
        if not isinstance(rule, dict) or rule.get("id") not in unresolved:
            continue
        missing = rule.get("missing") or ()
        if isinstance(missing, str):
            missing = (missing,)
        for key in missing:
            if key in available and key not in {"legal_basis", "complete_claim_price"}:
                return key
    for key in ("calculation", "additional_claims", "penalty_calculation", "period_payments", "costs", "litigation_costs", "requests", "amount", "claim_price", "fee"):
        if key in available:
            return key
    return None


def _plan_question(plan, field):
    question = plan.get("pending_question")
    if isinstance(question, str) and question.strip():
        return question.strip()
    unresolved = set(plan.get("unresolved_rule_ids") or ())
    for rule in plan.get("rules") or ():
        if not isinstance(rule, dict) or rule.get("id") not in unresolved:
            continue
        question = rule.get("question")
        if isinstance(question, str) and question.strip():
            return question.strip()
    return _FORMULA_FIELD_QUESTIONS.get(
        field,
        "Для подготовки файла нужно завершить расчёт и уточнить недостающие сведения.",
    )


def formula_export_issues(state, package=None):
    """Return export blockers before a formula slot can become ``[... ]``.

    Formula fields are managed values, not ordinary editable draft gaps.  A
    review-required/unknown value used to pass the generic interview readiness
    check and then become a bracket placeholder in both declarative and DOCX
    renderers.  Explicit ``not_applicable`` remains valid: it records a
    deliberate decision, including an optional monetary value that does not
    apply to the selected document.
    """
    scenario = SCENARIOS.get(state.get("scenario"))
    if scenario is None:
        return []
    fields = state.get("fields") or {}
    package = state.get("text_package") if package is None else package

    plan = state.get("calculation_plan")
    if isinstance(plan, dict) and plan.get("status") in {"needs_input", "review_required"}:
        unresolved = plan.get("unresolved_rule_ids") or ()
        if unresolved:
            field = _plan_issue_field(plan, scenario)
            if field:
                return [{
                    "field": field,
                    "code": "pending_calculation_plan",
                    "question": _plan_question(plan, field),
                }]

    issues = []
    for spec in scenario.fields:
        key = spec.key
        if key not in FORMULA_EXPORT_FIELDS or not field_is_active(spec, fields):
            continue
        if not _formula_field_is_rendered(package, key):
            continue
        # A sparse/migrated state can legitimately omit an untouched managed
        # slot.  Without a calculation plan there is no requested numerical
        # work to block, and returning an issue for a non-existent key makes
        # downstream editors try to reopen a field that was never collected.
        if key not in fields:
            continue
        item = fields.get(key) or {}
        status = item.get("status")
        if status == "not_applicable":
            continue
        # A value which was never requested as a calculation is an ordinary
        # labelled draft gap.  Treating every legacy ``unknown`` field or the
        # older form-rule marker ``assistant_review`` as a hard formula error
        # made an otherwise complete document impossible to export.  The
        # strict contract below still applies as soon as a calculation plan
        # exists, or when the field itself is an unresolved user/calculator
        # value.  This keeps an explicit 395/penalty/duty calculation from
        # leaking into a document while preserving draft support for every
        # template family.
        if status == "unknown":
            continue
        if status == "review_required" and item.get("origin") == "assistant_review":
            continue
        value = item.get("value")
        if status == "filled" and value is not None and str(value).strip():
            continue
        issues.append({
            "field": key,
            "code": "unresolved_formula_field",
            "question": _FORMULA_FIELD_QUESTIONS[key],
        })
    return issues


def readiness_report(state, package=None):
    scenario = SCENARIOS[state['scenario']]
    fields = state.get('fields', {})
    missing, review = [], []
    for spec in scenario.fields:
        if not field_is_active(spec, fields): continue
        item = fields.get(spec.key, {})
        status = item.get('status')
        if status == 'review_required':
            review.append({'field': spec.key, 'label': spec.label})
        elif status != 'filled' and not spec.optional:
            # An explicitly inapplicable field does not create a false gap.
            if status != 'not_applicable': missing.append({'field': spec.key, 'label': spec.label})
        elif status == 'filled' and not item.get('value'):
            missing.append({'field': spec.key, 'label': spec.label})
    coverage = (package or {}).get('coverage', 'basic')
    actions = []
    if fields.get('copy_status', {}).get('value') == 'не направлены':
        actions.append('Направить другим участникам копии иска и отсутствующих у них приложений и подготовить подтверждение отправки.')
    if state['scenario']=='claim_alimony_fixed':
        notice=fields.get('copy_notice',{})
        if notice.get('status')!='filled' or re.search(r'^нет|не (?:направ|отправ)|предстоит',notice.get('value') or '',re.I):
            actions.append('Направить участникам копии иска и отсутствующих у них приложений; приложить подтверждение направления по статье 132 ГПК РФ.')
    if (state['scenario'].startswith('claim_') and state['scenario']!='claim_alimony_fixed' and 'copy_status' not in fields) or state['scenario']=='order_alimony':
        notice=fields.get('copy_notice',{})
        if notice.get('status')!='filled' or re.search(r'^нет|не (?:направ|отправ)|предстоит',notice.get('value') or '',re.I):
            article='статье 124 ГПК РФ' if state['scenario']=='order_alimony' else 'применимым процессуальным требованиям'
            actions.append('Направить другой стороне копии заявления и приложений; подготовить подтверждение направления по '+article+'.')
    return {'status': 'incomplete_draft' if missing or review or actions else 'draft',
            'missing': missing, 'legal_review': review, 'coverage': coverage,
            'actions': actions,
            'lawyer_reviewed': (package or {}).get('review_status') == 'lawyer_reviewed'}


def catalog_audit():
    from app.services.document_template_library import load_text_package
    rows = []
    for scenario in SCENARIOS.values():
        package = load_text_package(scenario)
        rows.append({'scenario': scenario.key, 'family': scenario.family, 'title': scenario.title,
            'template_version': package['version'] if package else None,
            'coverage': (package or {}).get('coverage', 'basic'),
            'legal_review': (package or {}).get('review_status', 'unreviewed'),
            'questions': len(scenario.fields), 'issues': schema_issues(scenario, package) if package else ['missing_package']})
    return rows
