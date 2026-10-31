"""Normative profiles for the maintained catalog, separate from user facts.

Rules describe the legal framework, not a finding of liability or proof.
Amounts, penalties, a specific court and agreed terms never come from a sample.
"""
from copy import deepcopy
import re

GPK='https://www.consultant.ru/document/cons_doc_LAW_39570/'
APK='https://www.consultant.ru/document/cons_doc_LAW_37800/'
GK1='https://www.consultant.ru/document/cons_doc_LAW_5142/'
GK2='https://www.consultant.ru/document/cons_doc_LAW_9027/'
TK='https://www.consultant.ru/document/cons_doc_LAW_34683/'
SK='https://www.consultant.ru/document/cons_doc_LAW_8982/'
ZPP='https://www.consultant.ru/document/cons_doc_LAW_305/'
IP='https://www.consultant.ru/document/cons_doc_LAW_71450/'
NK='https://www.consultant.ru/document/cons_doc_LAW_28165/61fdaaad02ecf7772dc9e0331d21c7ddc3323d4f/'
APPEALS='https://www.consultant.ru/document/cons_doc_LAW_59999/'

# Original concise formulations. Each profile is linked to its statutory text.
PROFILES={
 'employment':('Содержание, срок и письменная форма трудового договора определяются статьями 57, 58 и 67 ТК РФ. Условия оплаты труда и сроки выплаты заработной платы согласуются с учётом статей 135 и 136 ТК РФ.',[TK,'https://mintrud.gov.ru/ministry/programms/trudotn/dogovor']),
 'housing':('Договор регулируется главой 35 ГК РФ. По статьям 671 и 674 ГК РФ наймодатель предоставляет гражданину жилое помещение для проживания на основании письменного договора. Статьи 676 и 678 ГК РФ определяют основные обязанности сторон, статьи 681–683 ГК РФ — вопросы ремонта, платы и срока найма. Прекращение договора и его последствия определяются с учётом статей 687 и 688 ГК РФ.',[GK2]),
 'housing_act':('Передача или возврат помещения фиксируются во исполнение договора найма. Статьи 309 и 310 ГК РФ предусматривают надлежащее исполнение обязательств и ограничивают односторонний отказ от их исполнения. Права и обязанности сторон найма определяются главой 35 ГК РФ. Подписание акта подтверждает только указанную в нём фактическую передачу и состояние имущества.',[GK1,GK2]),
 'addendum':('Соглашение заключается с учётом статей 450, 452 и 453 ГК РФ. Изменения договора оформляются по соглашению сторон в надлежащей форме; последствия изменения определяются законом и согласованными сторонами условиями.',[GK1]),
 'services':('По статьям 779 и 781 ГК РФ исполнитель оказывает согласованные услуги по заданию заказчика, а заказчик оплачивает их в предусмотренные договором сроки и порядке. Отказ от договора осуществляется с учётом статьи 782 ГК РФ. Обязательные права сторон и применимые правила защиты потребителя не могут быть отменены условиями договора.',[GK2]),
 'work':('Статьи 702, 708, 709 и 720 ГК РФ регулируют выполнение согласованной работы, её сроки, цену и приёмку результата. Требования к качеству и последствия недостатков определяются статьями 721–724 ГК РФ. Условия договора применяются с учётом обязательных требований закона.',[GK2]),
 'loan':('По статьям 807, 808 и 810 ГК РФ заёмщик обязан возвратить полученную сумму займа на согласованных условиях; передачу денег может подтверждать расписка или иной документ. Проценты определяются с учётом статьи 809 ГК РФ, последствия нарушения срока возврата — статьи 811 ГК РФ. Отсутствие записи о процентах само по себе не означает согласование беспроцентности.',[GK2]),
 'goods':('Статья 18 Закона РФ от 07.02.1992 № 2300-1 «О защите прав потребителей» предусматривает способы защиты при обнаружении недостатков товара. Условия выбора требования зависят от категории товара, характера недостатка и сроков обращения. Статьи 21 и 22 указанного Закона определяют сроки исполнения соответствующих требований. Неподтверждённые неустойки и убытки автоматически не начисляются.',[ZPP]),
 'defective_service':('Статьи 4 и 29 Закона РФ от 07.02.1992 № 2300-1 «О защите прав потребителей» регулируют качество работ и услуг и требования при обнаружении недостатков. Применимые сроки удовлетворения отдельных требований определяются статьями 30 и 31 указанного Закона. Выбранный способ защиты и основания денежных требований указываются в настоящем обращении отдельно.',[ZPP]),
 'late_delivery':('Статья 23.1 Закона РФ от 07.02.1992 № 2300-1 «О защите прав потребителей» устанавливает последствия нарушения согласованного срока передачи предварительно оплаченного товара. Потребитель вправе выбрать предусмотренное законом требование. Неустойка и убытки требуют отдельного расчёта с учётом фактических обстоятельств и установленных законом ограничений.',[ZPP]),
 'rent':('Обязательства должны исполняться надлежащим образом в соответствии со статьёй 309 ГК РФ; односторонний отказ от исполнения ограничен статьёй 310 ГК РФ. Обязанность арендатора своевременно вносить арендную плату предусмотрена статьёй 614 ГК РФ. Основной долг, проценты и неустойка подтверждаются договором, периодом просрочки и отдельным расчётом.',[GK1,GK2]),
 'supply':('Обязательства должны исполняться надлежащим образом в соответствии со статьёй 309 ГК РФ; односторонний отказ от исполнения ограничен статьёй 310 ГК РФ. По договору поставки покупатель оплачивает поставленные товары с учётом статей 506 и 516 ГК РФ. Основной долг, проценты и неустойка подтверждаются договором, поставочными документами и отдельным расчётом.',[GK1,GK2]),
 'consumer_agency':('Статья 40 Закона РФ от 07.02.1992 № 2300-1 «О защите прав потребителей» предусматривает государственный контроль в сфере защиты прав потребителей. Обращение рассматривается уполномоченным органом в установленном законом порядке. Прошу оценить изложенные обстоятельства в пределах компетенции органа; разрешение гражданского требования о взыскании денег не подменяется рассмотрением жалобы.',[ZPP,APPEALS]),
 'debt_services':('Обязательства подлежат надлежащему исполнению в соответствии со статьёй 309 ГК РФ; односторонний отказ ограничен статьёй 310 ГК РФ. Статьи 779 и 781 ГК РФ предусматривают оплату услуг в согласованные сроки и порядке. Задолженность и дополнительные денежные требования подтверждаются самостоятельным расчётом и доказательствами.',[GK1,GK2]),
 'deposit':('Обеспечительный платёж регулируется статьёй 381.1 ГК РФ. Основания его зачёта и возврата определяются законом и условиями договора; удержание должно иметь подтверждённое основание. Обязательства исполняются надлежащим образом с учётом статей 309 и 310 ГК РФ.',[GK1]),
 'damage':('Статья 15 ГК РФ предусматривает возмещение подтверждённых убытков, включая расходы на восстановление нарушенного права и повреждённого имущества. По статье 1064 ГК РФ имущественный вред по общему правилу возмещается причинителем вреда. Причина повреждения, связь действий ответственного лица с последствиями и размер ущерба подлежат подтверждению доказательствами.',[GK1,GK2]),
 'salary':('Статьи 21, 22 и 136 ТК РФ закрепляют обязанность работодателя своевременно и полностью выплачивать заработную плату. Расчёт при увольнении производится с учётом статьи 140 ТК РФ. Статья 236 ТК РФ предусматривает денежную компенсацию за нарушение установленных сроков выплат; её сумма определяется отдельно по фактическим данным.',[TK]),
 'reinstatement':('Основание и порядок прекращения трудового договора должны соответствовать ТК РФ, в том числе статье 84.1. Срок обращения в суд определяется с учётом статьи 392 ТК РФ. Статья 394 ТК РФ предусматривает последствия признания увольнения незаконным, включая восстановление на работе и соответствующие выплаты при наличии оснований.',[TK]),
 'resignation':('Заявление подаётся на основании статьи 80 ТК РФ. Дата прекращения трудового договора определяется с учётом установленного срока предупреждения, достигнутого сторонами соглашения либо предусмотренных законом обстоятельств. Окончательный расчёт и оформление прекращения трудовых отношений производятся по статьям 84.1 и 140 ТК РФ.',[TK]),
 'alimony_share':('Статья 80 СК РФ возлагает на родителей обязанность содержать несовершеннолетних детей. Размер алиментов в долях к заработку и иному доходу определяется по статье 81 СК РФ с учётом количества детей и обстоятельств дела. По статье 107 СК РФ алименты по общему правилу присуждаются с момента обращения в суд.',[SK]),
 'alimony_order':('Требование о взыскании алиментов на несовершеннолетних детей может быть рассмотрено в приказном порядке при соблюдении условий статьи 122 ГПК РФ, в частности при отсутствии требований об установлении или оспаривании отцовства и необходимости привлечения других заинтересованных лиц. Размер доли определяется с учётом статей 80 и 81 СК РФ; содержание заявления — статьи 124 ГПК РФ.',[GPK,SK]),
 'alimony_arrears':('Задолженность по алиментам определяется судебным приставом-исполнителем с учётом статьи 113 СК РФ и статьи 102 Федерального закона от 02.10.2007 № 229-ФЗ «Об исполнительном производстве». Расчёт зависит от исполнительного документа, установленного способа взыскания, периода и подтверждённых платежей должника.',[SK,IP]),
 'alimony_penalty':('Статья 115 СК РФ предусматривает ответственность за несвоевременную уплату алиментов. Для алиментов, установленных решением суда, закон предусматривает неустойку при образовании задолженности по вине обязанного лица; размер и период рассчитываются по каждому просроченному платежу. Условия ответственности по соглашению и основания уменьшения неустойки оцениваются отдельно.',[SK]),
 'divorce':('Основания и порядок расторжения брака судом определяются статьями 21–23 СК РФ с учётом ограничений статьи 17 СК РФ. Связанные вопросы о детях и иных требованиях разрешаются в пределах заявленных требований по статье 24 СК РФ. Отсутствие спора о детях или согласие второго супруга не предполагаются без подтверждения.',[SK]),
 'postpone':('По статьям 167 и 169 ГПК РФ участник сообщает суду о причинах неявки и представляет подтверждения. Вопрос об отложении разрешается судом с учётом уважительности причин и возможности рассмотрения дела. Само направление ходатайства не означает его удовлетворения.',[GPK]),
 'attach':('Статьи 35 и 57 ГПК РФ предусматривают право участников представлять доказательства и заявлять ходатайства. Относимость и допустимость представленных материалов оцениваются судом по правилам статей 59 и 60 ГПК РФ.',[GPK]),
 'costs':('Состав судебных расходов и их распределение определяются статьями 88, 94 и 98 ГПК РФ. Расходы на представителя рассматриваются по статье 100 ГПК РФ с учётом разумных пределов. Срок подачи отдельного заявления о расходах определяется статьёй 103.1 ГПК РФ.',[GPK]),
 'objection':('Статьи 35 и 149 ГПК РФ предусматривают право ответчика представить возражения и подтверждающие их доказательства. Каждая сторона доказывает обстоятельства, на которые ссылается, по правилам статьи 56 ГПК РФ. Несогласие с иском излагается в пределах конкретных требований истца.',[GPK]),
 'order_objection':('По статье 128 ГПК РФ должник вправе представить возражения относительно исполнения судебного приказа в течение десяти дней со дня получения его копии. Последствия поступления возражений и условия принятия поздних возражений определяются статьёй 129 ГПК РФ. Причины поздней подачи и подтверждения указываются отдельно, если срок пропущен.',[GPK]),
 'restore_term':('Статья 112 ГПК РФ предусматривает восстановление пропущенного процессуального срока при признании причин пропуска уважительными. Вместе с заявлением должно быть совершено соответствующее процессуальное действие с соблюдением специальных правил, если они установлены для него законом.',[GPK]),
 'writ':('Выдача исполнительного листа производится по статье 428 ГПК РФ с учётом вступления судебного акта в законную силу или оснований немедленного исполнения. Выдача дубликата ранее выданного и утраченного листа является отдельной процедурой, регулируемой статьёй 430 ГПК РФ.',[GPK]),
 'bailiff_complaint':('Статьи 121–124 Федерального закона от 02.10.2007 № 229-ФЗ «Об исполнительном производстве» предусматривают обжалование постановлений, действий и бездействия должностных лиц службы судебных приставов в порядке подчинённости. Срок обращения и требования к содержанию жалобы проверяются с учётом даты, когда заявителю стало известно о нарушении.',[IP]),
 'authority':('Доверенность оформляется с учётом статей 185 и 185.1 ГК РФ. Полномочия ограничены прямо указанными в настоящем документе действиями; случаи обязательного удостоверения определяются законом. По статье 186 ГК РФ дата совершения обязательна. Передоверие осуществляется только при соблюдении статьи 187 ГК РФ.',[GK1]),
 'appeal_civil':('Апелляционная жалоба на решение суда общей юрисдикции подаётся с соблюдением статей 321 и 322 ГПК РФ. Полномочия суда апелляционной инстанции и основания отмены или изменения решения определяются статьями 328 и 330 ГПК РФ. Доводы жалобы должны быть связаны с материалами дела и обжалуемым судебным актом.',[GPK]),
 'sale_nonresidential':('Договор продажи недвижимости заключается в письменной форме; существенные условия включают определение объекта и его цену. Передача недвижимости оформляется передаточным актом или иным документом о передаче. Переход права собственности подлежит государственной регистрации в предусмотренных законом случаях. Условия сделки применяются с учётом статей 549–556 ГК РФ.',[GK2]),
}

PROFILE_BY_FORM={
 'contract_employment':'employment',
 'contract_housing':'housing','act_housing_handover':'housing_act','act_housing_return':'housing_act','contract_housing_addendum':'addendum',
 'contract_services':'services','contract_work':'work','contract_loan':'loan','act_loan_receipt':'loan',
 'pretense_consumer_defective_goods':'goods','pretense_consumer_defective_service':'defective_service','pretense_consumer_late_delivery':'late_delivery','claim_consumer':'goods','claim_consumer_defective_goods':'goods','claim_consumer_late_delivery':'late_delivery','complaint_consumer_agency':'consumer_agency',
 'pretense_debt_loan':'loan','claim_debt_loan':'loan','pretense_debt_rent':'rent','claim_debt_rent':'rent','pretense_debt_services':'debt_services','claim_debt_services':'debt_services','pretense_debt_supply':'supply','claim_debt_supply':'supply','claim_rent_deposit':'deposit',
 'claim_damage_flood':'damage','pretense_damage_flood':'damage','claim_damage_property':'damage','pretense_damage_property':'damage',
 'claim_labor_salary':'salary','pretense_labor_settlement':'salary','claim_labor_reinstatement':'reinstatement','labor_resignation':'resignation',
 'order_alimony':'alimony_order','claim_alimony_share':'alimony_share','bailiff_alimony_arrears':'alimony_arrears','claim_alimony_penalty':'alimony_penalty','claim_divorce':'divorce',
 'motion_postpone':'postpone','motion_attach':'attach','motion_costs':'costs','motion_objection':'objection','motion_order_objection':'order_objection','motion_restore_term':'restore_term','motion_enforcement_writ':'writ',
 'complaint_bailiff_superior':'bailiff_complaint','power_of_attorney':'authority',
 'appeal_civil':'appeal_civil','contract_sale_nonresidential':'sale_nonresidential',
}


def uses_form_composer(state):
    return state.get('scenario') in PROFILE_BY_FORM and (state.get('text_package') or {}).get('composition')=='clause_document'


def commercial_procedure(state):
    fields=state.get('fields',{})
    procedure=(fields.get('procedure',{}).get('value') or '').lower()
    parties=[fields.get(k,{}).get('value') or '' for k in ('sender','recipient')]
    return bool(re.search(r'предпринимател|арбитраж',procedure) and all(re.search(r'\b(?:ООО|АО|ПАО|ИП)\b',p) for p in parties))


def _decimal_amount(value):
    """Return a stated monetary value without treating prose as a number."""
    from decimal import Decimal, InvalidOperation
    if value is None:
        return None
    try:
        amount=Decimal(str(value).replace('\u00a0','').replace(' ','').replace(',','.'))
    except InvalidOperation:
        return None
    return amount if amount >= 0 else None


def _confirmed_calculation_total(state):
    plan=state.get('calculation_plan',{})
    if isinstance(plan,dict) and plan.get('status')=='calculated' and plan.get('claim_price_total') is not None:
        return _decimal_amount(plan.get('claim_price_total'))
    ledger=state.get('calculation_ledger',{})
    if not isinstance(ledger,dict) or ledger.get('status')!='confirmed':
        return None
    return _decimal_amount(ledger.get('total'))


def _consumer_personal_use(state):
    fields=state.get('fields',{})
    # The universal consumer claim stores the same fact as ``procedure``;
    # specialised forms use ``consumer_status``.  Keep this legacy form-rule
    # path in sync with the shared calculation policy and reject an explicit
    # resale/business purpose instead of assuming consumer status from the
    # selected form.
    purpose=' '.join(str(fields.get(key,{}).get('value') or '')
                     for key in ('consumer_status','procedure','purpose','acquisition_purpose'))
    if re.search(r'перепродаж|предпринимател|коммерческ|бизнес|профессиональ',purpose,re.I):
        return False
    return bool(re.search(r'личн|семейн|домашн|для\s+себя|собственн\w*\s+потреблен',purpose,re.I))


def _confirmed_fee_field(fields):
    """Keep a concrete fee fact supplied by the user when no rule replaces it.

    The form rule layer owns only statutory exemptions.  It must not erase a
    receipt or a stated paid amount just because it cannot calculate a fee for
    the particular procedure itself.  Vague answers remain a review item.
    """
    stored=fields.get('fee',{})
    value=(stored.get('value') or '').strip()
    if stored.get('status')!='filled' or not value:
        return None
    if stored.get('origin') in {'verified_rule','assistant_review','arithmetic','composition_metadata'}:
        return None
    if re.search(r'\b(?:не\s+знаю|неизвест|уточн|провер|позже)\b',value,re.I):
        return None
    # A naked explanatory sentence is not evidence that the amount/receipt was
    # actually confirmed.  Accept a paid amount, a receipt/payment reference
    # or an explicit statutory exemption supplied by the user.
    if not re.search(r'\b(?:госпошлин|пошлин|квитанц|плат[её]ж|оплат|льгот|освобожд)\w*\b|\d+(?:[ \u00a0]\d{3})*(?:[.,]\d+)?\s*(?:руб|₽)',value,re.I):
        return None
    return {**stored,'status':'filled','error':None,
            'origin':stored.get('origin') or 'user_verified'}


def legal_profile(key):
    text,urls=PROFILES[PROFILE_BY_FORM[key]]
    text=text.replace('Неподтверждённые неустойки и убытки автоматически не начисляются.','Требования о неустойке и возмещении убытков подлежат самостоятельному обоснованию и расчёту.')
    text=text.replace('Прошу оценить изложенные обстоятельства в пределах компетенции органа; разрешение гражданского требования о взыскании денег не подменяется рассмотрением жалобы.','Меры по обращению принимаются в пределах компетенции органа с учётом установленных обстоятельств.')
    text=text.replace(' Отсутствие спора о детях или согласие второго супруга не предполагаются без подтверждения.','')
    if key.startswith('claim_'):
        text+=' Заявление и приложения оформляются с соблюдением применимых процессуальных требований.'
    return text,list(urls)


def prepare_form_rules(state):
    from app.services.document_scenarios import SCENARIOS
    key=state['scenario'];specs={f.key:f for f in SCENARIOS[key].fields}
    # Formula results are deterministic managed fields.  Re-evaluate a plan
    # when this function is reached through export or a legacy state, then do
    # not overwrite a verified calculated price/duty with the older fallback
    # rules below.
    from app.services.document_formula_intake import synchronize_formula_plan
    synchronize_formula_plan(state)
    text,urls=legal_profile(key)
    # Educational rules are exceptional.  They must never leak into an
    # ordinary employment contract merely because the template also supports
    # teachers and educators.
    if key=='contract_employment' and state['fields'].get('is_pedagogue',{}).get('value')=='да':
        text+=' Для педагогической работы применяются специальные требования главы 52 ТК РФ, в том числе к допуску к работе, рабочему времени и ежегодному оплачиваемому отпуску. Объём учебной нагрузки закрепляется в трудовом договоре с учётом применимых правил её определения и изменения.'
        urls+=['https://publication.pravo.gov.ru/document/0001202505070004']
    if key=='claim_consumer':
        category=(state['fields'].get('category',{}).get('value') or '').lower()
        if re.search(r'услуг|работ|ремонт|подряд',category):text,urls=PROFILES['defective_service']
    if key.startswith('claim_'):
        business=commercial_procedure(state)
        text+=' Применяются статьи 125 и 126 АПК РФ.' if business else ' Применяются статьи 131 и 132 ГПК РФ.'
        urls.append(APK if business else GPK)
    if 'legal_basis' in specs:
        state['fields']['legal_basis']={'status':'filled','value':text,'origin':'verified_rule','sources':urls,'checked_at':'2026-10-27','error':None}
    # A price can come from the transparent ledger, which is authoritative
    # only after all stated components agree.  Do not use a total the user
    # typed if it conflicts with the arithmetic.
    ledger_total=_confirmed_calculation_total(state)
    calculated_fee = state['fields'].get('fee', {})
    if 'fee' in specs and calculated_fee.get('origin') != 'calculation_plan':
        user_fee=_confirmed_fee_field(state['fields'])
        fee=None
        if key in {'claim_labor_salary','claim_labor_reinstatement'}:fee='Истец освобождён от уплаты государственной пошлины по подпункту 1 пункта 1 статьи 333.36 НК РФ.'
        elif key in {'claim_alimony_share','order_alimony'}:fee='Заявитель освобождён от уплаты государственной пошлины по подпункту 2 пункта 1 статьи 333.36 НК РФ.'
        elif (key in {'claim_consumer','claim_consumer_late_delivery','claim_consumer_defective_goods'}
                and _consumer_personal_use(state)
                and ledger_total is not None and ledger_total <= 1_000_000):
            fee=('Истец освобождён от уплаты государственной пошлины по иску о защите прав потребителя '
                 'при цене иска не более 1 000 000 рублей (пункт 3 статьи 17 Закона РФ «О защите прав '
                 'потребителей», подпункт 4 пункта 2 статьи 333.36 НК РФ).')
        if fee:
            state['fields']['fee']={'status':'filled','value':fee,'origin':'verified_rule','sources':[NK],'error':None}
        elif user_fee:
            state['fields']['fee']=user_fee
        else:
            state['fields']['fee']={'status':'review_required','value':None,'origin':'assistant_review','sources':[],'error':None}
    if 'jurisdiction' in specs:
        state['fields'].setdefault('jurisdiction',{'status':'review_required','value':None,'origin':'assistant_review'})
    calculated_price = state['fields'].get('claim_price', {})
    if 'claim_price' in specs and calculated_price.get('origin') != 'calculation_plan':
        from decimal import Decimal,InvalidOperation
        from app.services.document_case_composition import _money
        fields=state['fields'];amount=fields.get('amount',{})
        price=None
        if key in {'claim_divorce','claim_labor_reinstatement'} and not fields.get('calculation',{}).get('value'):
            price='Неимущественное требование'
        elif ledger_total is not None:
            price=_money(ledger_total)
        elif amount.get('status')=='filled':
            # The principal is sufficient only when other monetary demands
            # have explicitly been excluded or the complete calculation agrees.
            calculation=fields.get('calculation',{}).get('value') or ''
            if (re.search(r'дополнительн\w* начисления (?:отсутствуют|не заявляются)|только основной|только возврат (?:предварительной )?(?:оплаты|цены товара)|иные суммы не заявля',calculation,re.I)
                    or re.fullmatch(r'\s*(?:только\s+)?основной долг[.! ]*',calculation,re.I)):
                try:price=_money(Decimal(amount['value']))
                except InvalidOperation:pass
        elif key=='claim_alimony_penalty':
            raw=fields.get('penalty_calculation',{}).get('value') or ''
            total=re.search(r'(?:составляет|итого|общая сумма)\s*(\d+(?:[ ]\d{3})*(?:[.,]\d+)?)\s*руб',raw,re.I)
            if total:price=_money(total[1].replace(' ','').replace(',','.'))
        fields['claim_price']={'status':'filled' if price else 'review_required','value':price,'origin':'arithmetic' if price else 'assistant_review','sources':[GPK],'error':None}
