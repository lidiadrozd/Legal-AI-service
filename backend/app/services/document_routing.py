"""Require positive subject evidence before choosing a form from the catalog.

A classifier's confidence or the nearest embedding is not evidence that a
transaction occurred. These scopes also apply to future form adapters.
"""
import re


def requests_service_refund(text):
    """Evidence that the person seeks their payment back for a service."""
    return bool(re.search(
        r'\b(?:(?:хочу|прошу|требую)\s+вернуть|(?:иск|претензи\w*)\s+о\s+возврате)'
        r'\s+(?:мне\s+)?(?:оплат\w*|уплачен\w*|деньги|стоимост\w*)'
        r'|\b(?:мне|нам)\s+(?:так\s+и\s+)?не\s+оказа[лн]\w*'
        r'|\bнеоказанн\w*\s+услуг\w*', text, re.I))


def requests_service_payment(text):
    """The provider is collecting a fee; a customer's refund is a different claim."""
    if requests_service_refund(text):
        return False
    return bool(re.search(
        r'\b(?:взыска\w*|получить|требу\w*)\s+(?:неоплаченн\w*\s+|остат\w*\s+)?'
        r'(?:оплат\w*|вознаграждени\w*|долг\w*|задолженност\w*)\s+'
        r'(?:по\s+оплате\s+|за\s+|по\s+договору\s+)(?:оказанн\w*\s+|оказания\s+)?услуг\w*\b'
        r'|\bзаказчик\w*\s+(?:так\s+и\s+)?не\s+(?:полностью\s+)?оплатил\w*\s+(?:оказанн\w*\s+)?услуг\w*',
        text, re.I))


def describes_property_flood(text):
    """Use the same event evidence to select and validate a flood form."""
    if re.search(r'\b(?:залив(?:а|е|у|ом|ы|ов)?|затоплени[еяию])\b', text, re.I):
        return True
    for clause in re.split(r'[.!?;\n]', text):
        flooding = r'(?:залил[аои]?|заливали?|залит[аоы]?|затопил[аои]?|затоплен[аоы]?)'
        if re.search(rf'\b(?:нас|меня)\s+{flooding}\b|\b{flooding}\s+(?:нас|меня)\b', clause, re.I):
            return True
        housing = r'\b(?:квартир\w*|помещени\w*|жиль[еяёю]|потол(?:ок|к\w*)|сверху)\b'
        if re.search(rf'\b(?:{flooding}|протеч\w*|теч[её]т)\b', clause, re.I) and re.search(housing, clause, re.I):
            return True
        if re.search(r'\bвод[аы]\b.{0,20}(?:сверху|из квартиры)', clause, re.I):
            return True
    return False


SCOPES = {
    'contract_employment':r'(?:трудов|рудов)\w* (?:договор|контракт)|работа учител|работ[ау]\s+(?:учител|педагог)',
    'act_housing_handover':r'квартир|жил|найм', 'act_housing_return':r'квартир|жил|найм',
    'contract_housing_addendum':r'дополнител\w* соглашен',
    'claim_rent_deposit':r'депозит|обеспечительн\w* плат[её]ж',
    'pretense_rent_deposit':r'депозит|залог|обеспечительн\w* плат[её]ж',
    'claim_labor_salary':r'зарплат|заработн\w* плат|трудов|расч[её]т',
    'claim_labor_reinstatement':r'увольнен|восстанов.{0,20}работ',
    'labor_resignation':r'увольнен|уволить', 'pretense_labor_settlement':r'работодател|зарплат|увольнен|заработн\w* плат',
    'order_alimony':r'алимент', 'claim_alimony_share':r'алимент', 'claim_alimony_fixed':r'алимент',
    'bailiff_alimony_arrears':r'алимент', 'claim_alimony_penalty':r'алимент',
    'claim_divorce':r'развод|расторжен.{0,15}брак',
    'motion_order_objection':r'приказ', 'motion_restore_term':r'восстанов.{0,35}срок',
    'motion_enforcement_writ':r'исполнительн\w* лист', 'complaint_bailiff_superior':r'пристав|фссп',
    'debt_loan': r'расписк|за[её]м|займ|в долг|одолж',
    'debt_rent': r'аренд|найм|на[её]м|снимал|сдавал',
    'debt_services': r'услуг|исполнител|заказчик|оказал\w* работ',
    'debt_supply': r'поставк|поставлен\w* товар',
    'consumer_defective_goods': r'товар|покуп|купил|продав|магазин|продукт|телефон|ноутбук|диван|мебел|шкаф|кресл|матрас|стол|стул|кухн',
    'consumer_late_delivery': r'достав|предоплат|не (?:привез|прислал|получ)',
    'claim_consumer_defective_goods': r'товар|покуп|купил|продав|магазин|продукт|телефон|ноутбук|диван|мебел|шкаф|кресл|матрас|стол|стул|кухн',
    'claim_consumer_late_delivery': r'достав|предоплат|не (?:привез|прислал|получ)|срок.{0,20}(?:передач|товар|диван|мебел|шкаф|кресл|матрас|стол|стул|кухн)',
    'consumer_defective_service': r'услуг|ремонт|подряд|работ|химчистк',
    # A request against a managing organisation often names the claim before
    # it describes the particular damage event.  Do not reject that supported
    # form solely for using the usual wording "взыскать ущерб".
    'damage_property': r'повред|разбил|сломал|авари|дтп|наезд|причин[её]н\w*.{0,25}ущерб|(?:взыскан|возмещен)\w*.{0,35}ущерб|ущерб.{0,35}(?:взыскан|возмещен)',
    'claim_consumer': r'потребител|товар|купил|покуп|продав|магазин|услуг|телефон|ноутбук|диван|мебел|шкаф|кресл|матрас|стол|стул|кухн',
    'appeal_civil': r'гражданск|районн\w* суд|миров\w* судь',
    'appeal_arbitration': r'арбитраж',
    'complaint_consumer_agency': r'роспотребнадзор|потребител|магазин|товар|покуп',
    'complaint_labor_agency': r'трудов|работодател|зарплат|заработн\w* плат|роструд',
    'motion_postpone': r'отлож|перенос|перенести|не (?:смогу|могу).{0,20}(?:прийти|участв)|госпитал',
    'motion_attach': r'приобщ|прилож|добавить.{0,20}(?:доказател|документ)',
    'motion_costs': r'судебн\w* расход|расход\w* на (?:суд|представител|юрист)',
    'motion_objection': r'возраж|не соглас\w*.{0,20}иск',
    'contract_services': r'услуг|фотограф|фотосъ[её]м|видеосъ[её]м', 'contract_work': r'подряд|ремонт|работ|(?:создани|разработк|изготовлени)\w*\s+(?:веб[- ]?)?сайт',
    'contract_housing': r'найм|на[её]м|аренд|сда(?:ть|ю|вать)|сня(?:ть|тия)|снимать',
    'contract_loan': r'за[её]м|займ|в долг|одолж',
    'contract_sale_nonresidential': r'нежил\w* помещен',
    'act_services': r'услуг', 'act_work': r'работ|подряд',
    'act_loan_receipt': r'расписк|за[её]м|займ|в долг|одолж',
    'power_of_attorney': r'доверенност|представител|от моего имени',
}


def scope_text(state):
    return '\n'.join([state.get('request',''),state.get('context',''),*state.get('user_turns',[])])


def scenario_has_evidence(key,state):
    if key=='power_of_attorney':
        from app.services.document_authority_facts import is_authority_request
        return bool(re.search(SCOPES[key],scope_text(state),re.I) or is_authority_request(scope_text(state)))
    if key in {'appeal_civil','appeal_arbitration'}:
        from app.services.document_appeal_routing import appeal_proceeding
        return appeal_proceeding(scope_text(state)) == key.removeprefix('appeal_')
    topic=re.sub(r'^(?:claim|pretense)_','',key)
    if topic == 'damage_flood':
        return describes_property_flood(scope_text(state))
    if topic == 'debt_services' and requests_service_refund(scope_text(state)):
        return False
    pattern=SCOPES.get(key) or SCOPES.get(topic)
    return bool(pattern and re.search(pattern,scope_text(state),re.I))


def unavailable_form_message(state):
    from app.services.document_dialogue import document_kind
    if document_kind(state)=='appeal':
        from app.services.document_appeal_routing import appeal_clarification
        return appeal_clarification(scope_text(state))
    if re.search(r'алимент',scope_text(state),re.I):
        return ('Для ситуации с алиментами в библиотеке пока нет настроенной формы. '
            'Иск по договору оказания услуг для неё не подходит. '
            'Нужны отдельные формы для назначения алиментов и для вопросов уже возникшей задолженности; '
            'сейчас я не буду собирать сведения для неподходящего документа.')
    from app.services.document_dialogue import document_kind
    if document_kind(state)=='contract':
        return ('Этот вид договора пока не поддерживается готовыми формами сервиса. '
            'Описание сохранено. Сейчас можно подготовить трудовой договор, договор найма жилья, услуг, подряда или займа. '
            'Если нужна именно другая форма, я могу объяснить её основные условия в режиме консультации; '
            'непроверенный договор вместо неё формировать не буду.')
    return ('По вашему описанию пока не удалось выбрать форму. '
        'Укажите назначение документа: например, приобщить доказательства к делу, вернуть оплату, '
        'возразить против судебного приказа или заключить трудовой договор. '
        'Если нужная форма не поддерживается, я сообщу об этом и помогу разобрать необходимые сведения.')
