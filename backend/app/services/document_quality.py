"""Cross-field consistency checks shared by all interview scenarios."""
import re


def _words(value):
    return re.findall(r"[а-яё]+", value.casefold().replace("ё", "е"))


def quality_issues(state):
    fields = state.get("fields", {})
    def value(key):
        field = fields.get(key, {})
        return (field.get("value") or "") if field.get("status") == "filled" else ""
    from app.services.document_applicability import applicability_issues
    issues = applicability_issues(state)
    if value('place') and re.search(r'детск\w* сад|\bшкол(?:а|ы|е|у|ой)?\b|ООО|\bАО\b|организац|[«"]',value('place'),re.I):
        issues.append({'field':'place','code':'locality_required','question':'Место заключения — город или населённый пункт, а не название организации. В каком городе будет подписан документ?'})
    if state.get('scenario')=='contract_employment':
        authority=value('authority_basis')
        if authority and not re.search(r'устав|доверенн|решени\w*\s+о\s+назначен|приказ\w*\s+о\s+назначен|положени\w*\s+о\s+филиал',authority,re.I):
            issues.append({'field':'authority_basis','code':'authority_document_required','question':'Основание полномочий — это документ, а не только должность. Какой документ подтверждает право представителя работодателя подписать договор: устав, доверенность, решение или приказ о назначении? Если он неизвестен, можно оставить поле для проверки.'})
        if value('workplace') and re.search(r'поиск\w* работ|не (?:работаю|трудоустроен)|трудоустройство не оформлено',value('workplace'),re.I):
            issues.append({'field':'workplace','code':'future_workplace','question':'Нужно место будущей работы по этому договору. В каком подразделении и по какому адресу работник будет выполнять обязанности?'})
        if value('work_conditions') and re.search(r'законодательств|СанПиН|регулируют|приказом',value('work_conditions'),re.I) and not re.search(r'класс\w*\s*[1234]|СОУТ.{0,35}(?:от|№)',value('work_conditions'),re.I):
            issues.append({'field':'work_conditions','code':'sout_facts_missing','question':'Общие ссылки на нормы не описывают это рабочее место. Какой класс условий труда указан в карте СОУТ? Если документа нет, можно ответить «не знаю».'})
        schedule=value('schedule')
        payment=value('payment')
        pay_days=re.findall(r'(?<!\d)(?:[12]?\d|3[01])(?!\d)',payment)
        if len(set(pay_days))==1 and re.search(r'числ|кажд\w* месяц|раз в месяц',payment,re.I):
            issues.append({'field':'payment','code':'salary_twice_monthly','question':'Зарплата выплачивается не реже чем каждые полмесяца по статье 136 ТК РФ. Какие две конкретные даты выплаты установлены работодателем?'})
        hours=re.search(r'(\d{1,2}):(\d{2})\s*[-–—]\s*(\d{1,2}):(\d{2})',schedule)
        if not hours:hours=re.search(r'с\s*(\d{1,2}):(\d{2})\s*до\s*(\d{1,2}):(\d{2})',schedule)
        if hours and re.search(r'пн\s*[-–—]\s*пт|понедельник\w*\s+по\s+пятниц',schedule,re.I) and not re.search(r'смен|суммирован|перерыв|обед',schedule,re.I):
            daily=int(hours[3])+int(hours[4])/60-int(hours[1])-int(hours[2])/60
            if daily*5>40:issues.append({'field':'schedule','code':'working_time_clarification','question':'Этот интервал — время работы учреждения или личная смена работника? Уточните перерывы, чередование смен и учёт времени: пять таких смен превышают обычную продолжительность недели.'})
        if re.search(r'сверхуроч',value('pay_conditions'),re.I) and re.search(r'\d+.{0,25}(?:в нед|за нед|в месяц)',value('pay_conditions'),re.I) and not re.search(r'сверх (?:обязательн|повышенн)|дополнительно к|не (?:менее|ниже).{0,20}(?:152|полутор|двойн)',value('pay_conditions'),re.I):
            issues.append({'field':'pay_conditions','code':'overtime_not_flat_fee','question':'Фиксированная доплата не должна заменять обязательную повышенную оплату сверхурочных часов. Указанная сумма согласована дополнительно к такому расчёту или вместо него?'})
    if state.get('scenario')=='claim_alimony_fixed':
        from app.services.document_case_facts import fact
        from decimal import Decimal, InvalidOperation
        budget=fact(state,'child_budget')
        monthly=value('monthly_amount')
        if fact(state,'half_child_budget') and budget and monthly:
            try:
                if Decimal(monthly)!=Decimal(budget)/2:
                    issues.append({'field':'monthly_amount','code':'inconsistent_child_budget',
                        'question':'Просимая сумма не совпадает с половиной указанных расходов на ребёнка. Какую ежемесячную сумму оставляем и как она рассчитана?'})
            except InvalidOperation:
                issues.append({'field':'monthly_amount','code':'invalid_child_amount','question':'Какую точную ежемесячную сумму алиментов указываем в рублях?'})
    sender, recipient = _words(value("sender")), _words(value("recipient"))
    from app.services.document_export_contract import UNCERTAIN, clean_requisite
    scenario = state.get('scenario', '')
    if scenario:
        from app.services.document_scenarios import SCENARIOS, field_is_active
        from app.services.document_addresses import address_error
        from app.services.document_field_safety import field_value_problem, problem_question
        for spec in SCENARIOS[scenario].fields:
            if spec.kind == 'address' and field_is_active(spec, fields) and value(spec.key):
                error = address_error(value(spec.key))
                if error: issues.append({'field': spec.key, 'code': 'incomplete_address', 'question': error})
            if (spec.kind == 'text' and spec.key not in {'case_number', 'cadastral_number'} and field_is_active(spec, fields) and value(spec.key)
                    # A canonical authority can be set by the router from the
                    # explicit request (for example, "Государственная
                    # инспекция труда").  It may coincide with the UI label,
                    # but it is not a user copying a label into a fact slot.
                    # Source-bound extraction preserves a directly stated
                    # official addressee as well.  Its value may happen to
                    # equal a UI label (for example, "Государственная
                    # инспекция труда"), but it is not a copied placeholder.
                    and fields.get(spec.key, {}).get('origin') not in {'explicit_request_target', 'source_bound_extraction'}):
                problem = field_value_problem(spec.key, value(spec.key), spec.label)
                # Numeric phrase values such as an area are facts, not copied
                # prompt labels.  The generic label gate cannot infer their
                # type from a bare number, so keep the exception intentionally
                # narrow and only for a declared short phrase slot.
                if (problem == 'label_echo' and state.get('text_package', {}).get('field_formats', {}).get(spec.key) == 'phrase'
                        and re.fullmatch(r'\d+(?:[.,]\d+)?(?:\s*(?:кв\.?\s*м|м²|м2|процент(?:а|ов)?|%)?)?', value(spec.key).strip(), re.I)):
                    problem = None
                # A share in an alimony document is a typed scalar fact, for
                # example "1/4". The word-based label guard sees no words in
                # it and would otherwise reject the value as an empty label.
                if problem == 'label_echo' and spec.key == 'share' and re.fullmatch(r'\d{1,2}\s*/\s*\d{1,2}', value(spec.key).strip()):
                    problem = None
                # ISO and dotted calendar dates are similarly typed facts.
                # The label detector deliberately ignores digits, so without
                # this exception a value such as "2026-11-10" appears empty.
                if (problem == 'label_echo' and (spec.key == 'date' or spec.key.endswith('_date'))
                        and re.fullmatch(r'(?:\d{4}-\d{2}-\d{2}|\d{1,2}[./]\d{1,2}[./]\d{2,4})', value(spec.key).strip())):
                    problem = None
                if problem:
                    issues.append({'field': spec.key, 'code': problem, 'question': problem_question(problem)})
        # Template packages may declare identifier-like requisites beyond the
        # historical common set (for example, the first-instance court,
        # cadastral number or party bank details).  They deliberately bypass
        # prose editing, but not the same formal-style gate used for all other
        # document data; otherwise a conversational answer could enter a DOCX
        # merely because a new template named its slot "requisite".
        from app.services.document_form_composition import REQUISITES, requisite_keys
        from app.services.document_export_contract import formal_text
        labels = {spec.key: spec.label for spec in SCENARIOS[scenario].fields}
        for key in requisite_keys(state) - REQUISITES:
            raw = value(key)
            if not raw:
                continue
            cleaned = clean_requisite(key, raw)
            if not cleaned or not formal_text(cleaned):
                label = labels.get(key, key)
                issues.append({'field': key, 'code': 'unclean_template_requisite',
                    'question': f'Реквизит «{label}» содержит разговорное, неполное или служебное пояснение. Укажите точное значение без комментариев.'})
    if value('requests') and re.search(r'решить (?:вопрос|проблем\w*)|разобраться (?:с|со)\b', value('requests'), re.I):
        issues.append({'field': 'requests', 'code': 'indefinite_request',
            'question': 'Какое конкретное действие просите выполнить? Если нужно только денежное возмещение, так и напишите.'})
    if sender and recipient and sender == recipient:
        issues.append({'field': 'recipient', 'code': 'same_parties',
            'question': 'Заявитель и адресат указаны как одно лицо. Кому должен быть адресован документ? Укажите другую сторону или ведомство.'})
    # A nickname or a single ordinary word is not a sufficiently reliable
    # legal name when the conversation itself says the opposing side is an
    # organisation (for example, a management company or shop).  Do not guess
    # an LLC/individual-entrepreneur form: ask for the exact wording from a
    # receipt, agreement or public record.
    context = ' '.join([state.get('request', ''), state.get('context', ''), value('facts'), value('event'), value('responsibility')])
    organisation_context = bool(re.search(r'управляющ\w*\s+компан|\bук\b|\bтсж\b|магазин\w*|продавец\w*|организац\w*|компан\w*|юр(?:идическ\w*)? лиц', context, re.I))
    bare_name = re.fullmatch(r'[А-Яа-яЁё-]{3,}', value('recipient').strip())
    if organisation_context and bare_name and not re.search(r'\b(?:ооо|ао|пао|зао|оао|ип|ук|тсж|жск)\b|[«"]', value('recipient'), re.I):
        issues.append({'field': 'recipient', 'code': 'official_organisation_name_required',
            'question': 'Для организации нужно точное официальное наименование, как в квитанции, договоре или реестре. Укажите его вместе с известной организационно-правовой формой; не буду угадывать форму по короткому названию.'})
    employer = _words(value('employer'))
    if sender and employer and sender == employer:
        issues.append({'field': 'employer', 'code': 'self_employer',
            'question': 'Вместо работодателя указаны ФИО заявителя. Как называется работодатель, на которого подаёте жалобу?'})
    if scenario.startswith('complaint_') and recipient and not re.search(r'инспекц|роструд|роспотребнадзор|управлен|служб|прокуратур|ведомств|пристав|фссп', value('recipient'), re.I):
        issues.append({'field': 'recipient', 'code': 'authority_role',
            'question': 'Адресатом этой жалобы должно быть ведомство, а не заявитель или работодатель. Какое ведомство указать?'})
    signature = _words(value('signature'))
    if signature and recipient and signature == recipient and sender != recipient:
        issues.append({'field': 'sender', 'code': 'opponent_signer',
            'question': 'Подписантом указан человек из другой стороны дела. От чьего имени подаётся документ и кто его подпишет?'})
    if value('court') and (UNCERTAIN.search(value('court')) or not clean_requisite('court', value('court'))):
        issues.append({'field': 'court', 'code': 'uncertain_court',
            'question': 'Название суда указано предположительно. Какое точное наименование стоит в повестке или судебном документе? Если пока неизвестно, оставим поле для заполнения.'})
    if value('case_number') and not re.search(r'\d', clean_requisite('case_number', value('case_number')) or ''):
        issues.append({'field': 'case_number', 'code': 'invalid_case_number',
            'question': 'Какой номер дела указан в судебном документе? Если неизвестен, оставим поле для заполнения.'})
    from app.services.document_export_contract import ROLE_FIELDS, CHATTER
    for key in ROLE_FIELDS - {'court'}:
        if value(key) and CHATTER.search(value(key)):
            issues.append({'field': key, 'code': 'unclean_requisite',
                'question': 'Этот реквизит содержит разговорное пояснение. Какое точное имя, наименование или реквизит нужно указать в документе?'})
    details = _words(value('party_details'))
    if details and details in (sender, recipient):
        issues.append({'field': 'party_details', 'code': 'misplaced_identity',
            'question': 'В дополнительные реквизиты попало только имя или название стороны. Какие идентификаторы или контакты сторон известны? Если неизвестны, так и напишите.'})
    payment = _words(value("payment_details"))
    if len(recipient) == 3 and sender != recipient and all(token in payment for token in recipient):
        issues.append({"field": "payment_details", "code": "counterparty_payee",
            "question": "В реквизитах получателем денег указана другая сторона документа. Какие реквизиты получателя платежа нужно указать вместо них? Если они неизвестны, так и напишите."})
    if len(sender) == 3:
        for key, field in fields.items():
            if key in {"sender", "recipient", "signature", "counterparty_signature"} or field.get("status") != "filled":
                continue
            raw = field.get("value") or ""
            # Same surname/name with a different patronymic is a conflict, not
            # permission for the model to choose a person's identity.
            for name in re.findall(r"\b[А-ЯЁ][а-яё-]+\s+[А-ЯЁ][а-яё-]+\s+[А-ЯЁ][а-яё-]+", raw):
                tokens = _words(name)
                if (len(tokens) == 3 and tokens[0][:5] == sender[0][:5] and tokens[1][:4] == sender[1][:4]
                        and tokens[2][:6] != sender[2][:6]):
                    issues.append({"field": "sender", "code": "conflicting_identity",
                        "question": "В сведениях о заявителе и описании обстоятельств указаны разные отчества. Какое полное ФИО заявителя верно?"})
                    break
            if any(item["code"] == "conflicting_identity" for item in issues):
                break
    for key in ("signature", "counterparty_signature"):
        if value(key) and re.search(r"@|\d{5}|\+\d", value(key)):
            issues.append({"field": key, "code": "invalid_signer",
                "question": "В поле подписанта попали контактные данные. Кто подпишет документ: укажите его полное ФИО?"})
    # Formula fields have a stricter export contract than ordinary draft
    # prose: an unresolved value would otherwise become a bracket placeholder
    # in the generated document.  Keep the check here so both the explicit
    # export endpoint and the chat's automatic file path stop before rendering.
    from app.services.document_schema import formula_export_issues
    issues.extend(formula_export_issues(state))
    return issues


def clean_agreement(value):
    """Keep provenance notes in JSON, not in a legal document's prose."""
    parts = re.split(r"\s*Уточнение пользователя:\s*", value, maxsplit=1, flags=re.I)
    if len(parts) == 1:
        return value
    base, note = parts
    year = re.match(r"((?:19|20)\d{2})\s*(?:год|г\.)", note, re.I)
    if not year:
        raise ValueError("Нужно уточнить основание обязательства: служебная заметка содержит неразобранные факты.")
    remainder = note[year.end():].strip(" .,;\n")
    if remainder and not re.fullmatch(r"(?:(?:факт[ы]?|фак[ы]?|подтверждение)\s*[:—-]?\s*)?расписка[. ]*", remainder, re.I):
        raise ValueError("Нужно разобрать дополнительные факты об основании обязательства перед подготовкой файла.")
    if "20__" in base:
        base = base.replace("20__", year[1])
    elif not re.search(r"\b(?:19|20)\d{2}\b", base):
        base = base.rstrip(". ") + " " + year[1] + " года."
    if re.search(r"расписк", note, re.I) and not re.search(r"расписк", base, re.I):
        base = base.rstrip(". ") + ". Подтверждающий документ: расписка."
    return base
