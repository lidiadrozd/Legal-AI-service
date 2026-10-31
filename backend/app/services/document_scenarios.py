"""Versioned scenario definitions. Texts are original draft structures, not GARANT exports.

Keep legal variants separate. A catalog entry is never evidence of legal review.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    question: str
    kind: str = "text"
    optional: bool = False
    when_field: str | None = None
    when_values: tuple[str, ...] = ()
    choices: tuple[str, ...] = ()


def field(key, label, question=None, kind="text", optional=False, *, when_field=None, when_values=(), choices=()):
    return Field(key, label, question or f"Укажите: {label.lower()}.", kind, optional, when_field, tuple(when_values), tuple(choices))


COMMON = (
    field("sender", "Заявитель / сторона 1", "Укажите полное ФИО или наименование первой стороны. Неизвестные реквизиты можно вписать позже."),
    field("sender_address", "Адрес первой стороны", kind="address"),
    field("recipient", "Адресат / сторона 2"),
    field("recipient_address", "Адрес второй стороны", kind="address"),
)
FACTS = field("facts", "Обстоятельства", "Опишите, что произошло, когда и чем это подтверждается.")
AMOUNT = field("amount", "Основная сумма", "Какова точная сумма в рублях, без дополнительных начислений?", "money")
AGREEMENT = (
    field("agreement", "Договор и его дата", "Какой договор заключён, когда, есть ли номер и письменный документ?"),
    field("due_date", "Срок исполнения обязательства", kind="date"),
)
ENDING = (
    field("attachments", "Приложения", "Какие документы приложите? Если приложений нет, так и напишите."),
    field("date", "Дата документа", kind="date"),
    field("signature", "Подписант", "Кто подпишет документ? Укажите ФИО и основание полномочий представителя, если он есть."),
)
COURT = (
    field("procedure", "Процессуальный порядок", "Спор связан с личными нуждами граждан или с предпринимательской деятельностью?"),
    field("court", "Суд и адрес", "Укажите суд и его адрес; если ещё не определили суд, сообщите об этом."),
    field("party_details", "Дополнительные сведения о сторонах", "Укажите известные идентификаторы, контакты и данные сторон для выбранного порядка рассмотрения; неизвестные сведения можно оставить для заполнения."),
)
CLAIM = (
    field("pretrial", "Досудебное урегулирование", "Направлялась ли претензия: когда, каким способом, есть ли подтверждение и ответ?"),
    field("calculation", "Расчёт требований", "Из чего складывается сумма требований? Укажите расчёт и периоды; проценты и неустойку без основания не добавляем."),
    field("legal_basis", "Проверенное правовое обоснование", "Есть ли проверенное правовое обоснование требований? Если нет, оставим этот раздел для проверки."),
    field("fee", "Госпошлина / основание льготы", "Укажите проверенный размер госпошлины и подтверждение оплаты либо основание льготы. Если неизвестно, сообщите."),
    field("requests", "Требования к суду", "Что именно просите взыскать или обязать сделать? Перечислите требования отдельно."),
)


@dataclass(frozen=True)
class Scenario:
    key: str
    family: str
    title: str
    fields: tuple[Field, ...]
    version: int = 1
    review_status: str = "draft_structure"
    source: str = "original_structure"

    def as_dict(self):
        from dataclasses import asdict
        return asdict(self)


SCENARIOS: dict[str, Scenario] = {}


def add(key, family, title, specific, *, court=False, claim=False):
    fields = COMMON + (COURT if court else ()) + tuple(specific) + (CLAIM if claim else ()) + ENDING
    assert len({f.key for f in fields}) == len(fields), key
    SCENARIOS[key] = Scenario(key, family, title, fields)


DEBT_TYPES = {
    "loan": ("займа", field("transfer", "Передача займа", "Опишите передачу денег: дату, способ, получателя и подтверждающий документ.")),
    "rent": ("аренды", field("property", "Объект аренды и период долга", "Что передано в аренду и за какие периоды не внесена плата?")),
    "services": ("оказания услуг", field("performance", "Оказанные услуги", "Какие услуги, когда оказаны, как подтверждены исполнение и приёмка?")),
    "supply": ("поставки", field("goods", "Поставка товара", "Опишите поставку: товар, дату, количество и документы о приёмке.")),
}
for suffix, (name, extra) in DEBT_TYPES.items():
    details = AGREEMENT + (extra, FACTS, AMOUNT)
    add(f"pretense_debt_{suffix}", "debt_pretense", f"Претензия о задолженности по договору {name}", details + (
        field("requests", "Требования", "Что требуете от адресата и на каком основании?"),
        field("response_term", "Срок исполнения требования", "Какой срок исполнения требования установлен договором или выбран вами? Неизвестный срок оставим для проверки."),
    ))
    add(f"claim_debt_{suffix}", "debt_claim", f"Иск о задолженности по договору {name}", details, court=True, claim=True)

for suffix, title, questions in (
    ("defective_goods", "Возврат денег за некачественный товар", (
        field("purchase", "Покупка", "Что, когда, у кого и за какую сумму куплено?"),
        field("defect", "Недостатки товара", "Какие недостатки обнаружены, когда, проводились ли ремонт или экспертиза?"),
        field("goods_category", "Категория товара", "Укажите вид и модель товара, чтобы можно было проверить его категорию."))),
    ("late_delivery", "Возврат денег при просрочке доставки", (
        field("purchase", "Заказ и оплата", "Что заказано, когда оплачено, какова сумма предоплаты?"),
        field("delivery_date", "Согласованный срок доставки", kind="date"))),
    ("defective_service", "Недостатки работ или услуг", (
        field("service", "Работа или услуга", "Какая работа или услуга заказана, когда и за какую цену?"),
        field("defect", "Недостатки и обращения исполнителю", "Какие недостатки обнаружены и обращались ли вы за их устранением?"))),
):
    add(f"pretense_consumer_{suffix}", "consumer_pretense", f"Претензия: {title.lower()}", tuple(questions) + (FACTS, AMOUNT,
        field("consumer_status", "Цель приобретения", "Приобретение для личных нужд или предпринимательской деятельности?"),
        field("requests", "Выбранное требование", "Какого результата хотите: возврат денег, устранение недостатков, уменьшение цены или другое?")))

for suffix, title in (("flood", "ущерб от залива квартиры"), ("property", "имущественный ущерб")):
    details = (field("damage_object", "Повреждённое имущество"), FACTS, AMOUNT,
        field("responsibility", "Причина ущерба и связь с адресатом", "Что стало причиной ущерба и чем подтверждается ответственность адресата?"),
        field("evidence", "Подтверждение и оценка ущерба", "Есть ли акт, фото, заключение оценщика, смета или чеки?"))
    add(f"pretense_damage_{suffix}", "damage_pretense", f"Претензия: {title}", details + (field("requests", "Требование о возмещении"),))
    add(f"claim_damage_{suffix}", "other_claim", f"Иск: {title}", details, court=True, claim=True)
add("claim_consumer", "other_claim", "Иск о защите прав потребителя", (
    field("purchase", "Приобретение и его цель"), field("violation", "Нарушение прав потребителя"), FACTS, AMOUNT,
    field("seller_response", "Обращения продавцу / исполнителю и ответы")), court=True, claim=True)

for suffix, title in (("civil", "по гражданскому делу"), ("arbitration", "по арбитражному делу")):
    add(f"appeal_{suffix}", "complaint", f"Апелляционная жалоба {title}", (
        field("case_number", "Номер дела"), field("first_court", "Суд первой инстанции"),
        field("challenged_act", "Обжалуемый акт и дата его принятия"),
        field("act_date", "Дата изготовления решения в окончательной форме", kind="date"),
        field("grounds", "Основания обжалования", "С какими выводами суда не согласны и какими материалами дела это подтверждается?"),
        field("appeal_term", "Соблюдение срока обжалования", "Когда получен акт, проверен ли срок обжалования, требуется ли его восстановление?"),
        field("fee", "Госпошлина / льгота"), field("requests", "Просьба к апелляционному суду")), court=True)
for suffix, title, issue in (("consumer_agency", "Жалоба в Роспотребнадзор", "нарушение прав потребителя"),
                             ("labor_agency", "Жалоба в трудовую инспекцию", "нарушение трудовых прав")):
    add(f"complaint_{suffix}", "complaint", title, (FACTS,
        field("violation", "Нарушение", f"Опишите {issue} и даты событий."),
        field("previous_contact", "Предыдущие обращения и ответы"), field("requests", "Просьба к ведомству")))
# The authority receiving a complaint and the employer complained about are
# different parties; keeping separate slots prevents role substitution.
from dataclasses import replace
_labor = SCENARIOS["complaint_labor_agency"]
SCENARIOS[_labor.key] = replace(_labor, fields=_labor.fields[:4] + (
    field("employer", "Работодатель", "Как называется работодатель, на которого подаёте жалобу?"),
    field("employer_address", "Адрес работодателя", "Какой адрес работодателя вам известен? Если неизвестен, оставим поле для заполнения.", "address"),
) + _labor.fields[4:], version=2)
for suffix, title, details in (
    ("postpone", "Ходатайство об отложении заседания", (field("hearing_date", "Дата заседания", kind="date"), field("reasons", "Причины и подтверждения невозможности участия"))),
    ("attach", "Ходатайство о приобщении документов", (field("documents", "Приобщаемые документы"), field("relevance", "Значение документов для дела"))),
    ("costs", "Заявление о взыскании судебных расходов", (AMOUNT, field("costs", "Расходы и подтверждения оплаты"), field("outcome", "Результат рассмотрения дела и даты судебных актов"))),
    ("objection", "Возражения на иск", (field("claims", "Требования истца"), field("objections", "Возражения и подтверждающие доказательства"))),
):
    add(f"motion_{suffix}", "procedural", title, (field("case_number", "Номер дела"),) + details + (field("requests", "Просьба к суду"),), court=True)
for suffix, title, specific in (
    ("services", "Договор оказания услуг", (field("subject", "Перечень услуг и результат"), field("acceptance", "Порядок оказания и приёмки услуг"))),
    ("work", "Договор подряда", (field("subject", "Работы и их результат"), field("materials", "Материалы и техническое задание"), field("acceptance", "Приёмка результата и устранение недостатков"))),
    ("housing", "Договор найма жилого помещения", (field("property", "Полный адрес и описание жилья", kind="address"), field("ownership", "Основание права наймодателя"), field("residents", "Проживающие лица"), field("utilities", "Коммунальные платежи и обеспечительный платёж"))),
    ("loan", "Договор займа", (field("transfer", "Порядок передачи денег"), field("interest", "Процентный или беспроцентный заём и согласованные условия"), field("repayment", "Порядок возврата займа"))),
):
    add(f"contract_{suffix}", "contract", title, specific + (AMOUNT,
        field("term", "Сроки исполнения / действия"), field("payment", "Порядок оплаты / расчётов"),
        field("termination", "Изменение и прекращение договора"), field("liability", "Согласованные условия ответственности"),
        field("details", "Реквизиты сторон")))
for suffix, title, details in (
    ("services", "Акт оказанных услуг", (field("performance", "Оказанные услуги и период"), field("quality", "Замечания к услугам или их отсутствие"))),
    ("work", "Акт выполненных работ", (field("performance", "Выполненные работы и результат"), field("quality", "Замечания к работам или их отсутствие"))),
    ("loan_receipt", "Расписка о получении займа", (field("transfer", "Когда и как деньги фактически получены"), field("repayment", "Срок и условия возврата"), field("interest", "Условия о процентах"))),
):
    add(f"act_{suffix}", "act", title, (field("agreement", "Основание / договор"),) + details + (AMOUNT,))
add("power_of_attorney", "authority", "Доверенность на внесудебные действия", (
    field("principal_details", "Данные доверителя"), field("agent_details", "Данные представителя"),
    field("powers", "Конкретные полномочия", "Какие именно действия и перед кем поручаете совершить?"),
    field("validity", "Срок действия"), field("substitution", "Условия передоверия"),
    field("form_check", "Проверка формы доверенности", "Проверено ли требование к форме доверенности для этих действий? Если нет, укажите, что требуется проверка.")))

add("contract_sale_nonresidential", "contract", "Договор купли-продажи нежилого помещения", (
    field("seller_details", "Реквизиты продавца", "Какие реквизиты продавца известны? Неизвестные можно вписать позже."),
    field("buyer_details", "Реквизиты покупателя", "Какие реквизиты покупателя известны? Неизвестные можно вписать позже."),
    field("property_address", "Адрес помещения", "По какому полному адресу находится помещение?", "address"),
    field("cadastral_number", "Кадастровый номер", "Какой кадастровый номер помещения указан в выписке ЕГРН?"),
    field("area", "Площадь помещения", "Какова площадь помещения в квадратных метрах?"),
    field("property_description", "Описание помещения", "Как помещение описано в выписке ЕГРН?"),
    field("ownership", "Основание права продавца", "На основании какого документа продавцу принадлежит помещение?"),
    field("encumbrances", "Обременения и права третьих лиц", "Известны ли обременения или права третьих лиц на помещение?"),
    field("land_rights", "Права на землю", "Какие сведения о правах на землю относятся к этой сделке? Можно оставить для проверки."),
    AMOUNT,
    field("payment_method", "Порядок оплаты", "Как стороны договорились произвести оплату?"),
    field("payment_date", "Срок оплаты", "В какой срок покупатель должен оплатить помещение?"),
    field("payment_details", "Платёжные реквизиты", "Какие платёжные реквизиты нужно указать?"),
    field("handover", "Передача помещения", "Когда продавец должен передать помещение по акту?"),
    field("registration", "Регистрация перехода права", "Как стороны договорились организовать регистрацию перехода права?"),
    field("expenses", "Расходы по сделке", "Как стороны договорились распределить расходы по сделке?"),
    field("additional_terms", "Дополнительные условия", "Какие дополнительные условия согласованы сторонами? Можно ответить «нет»."),
))

# Fields needed by the sourced text templates, including both signatures and
# procedural requisites that must not disappear into an unstructured narrative.
from dataclasses import replace
for _key, _scenario in tuple(SCENARIOS.items()):
    _extra = []
    if _scenario.family in {"contract", "act", "authority"}:
        _extra.append(field("place", "Место составления", "В каком населённом пункте составляется документ?"))
    if _scenario.family in {"contract", "act"} and _key != "act_loan_receipt":
        _extra.append(field("counterparty_signature", "Подписант второй стороны", "Кто подпишет документ от второй стороны? Укажите ФИО и полномочия представителя, если он есть."))
    if _scenario.family in {"debt_pretense", "consumer_pretense", "damage_pretense", "debt_claim", "other_claim"}:
        _extra.append(field("payment_details", "Реквизиты для исполнения требования", "Как адресат может исполнить денежное требование: банковский перевод по каким реквизитам или другой согласованный способ?"))
    if _scenario.family in {"debt_claim", "other_claim", "procedural"} or _key.startswith("appeal_"):
        _extra.extend((field("jurisdiction", "Основание выбора суда и порядка", "Какие сведения подтверждают выбор этого суда и порядка? Если выбор ещё не проверен, так и сообщите."),
                       field("other_participants", "Другие участники дела", "Есть ли другие участники дела? Укажите их процессуальное положение, имена или наименования и адреса либо сообщите об отсутствии."),
                       field("copy_notice", "Направление копий участникам", "Кому, когда и как направлены копии документа и отсутствующих у них приложений? Укажите подтверждения либо что отправка ещё не выполнена.")))
    if _extra:
        SCENARIOS[_key] = replace(_scenario, fields=_scenario.fields[:-len(ENDING)] + tuple(_extra) + ENDING)

for _key, _scenario in tuple(SCENARIOS.items()):
    if _key.startswith("claim_"):
        _roles = ("Истец", "Ответчик")
    elif _key in {"contract_services", "act_services"}:
        _roles = ("Заказчик", "Исполнитель")
    elif _key in {"contract_work", "act_work"}:
        _roles = ("Заказчик", "Подрядчик")
    elif _key == "contract_housing":
        _roles = ("Наймодатель", "Наниматель")
    elif _key == "contract_loan":
        _roles = ("Займодавец", "Заёмщик")
    elif _key == "contract_sale_nonresidential":
        _roles = ("Продавец", "Покупатель")
    elif _key == "act_loan_receipt":
        _roles = ("Заёмщик", "Займодавец")
    elif _key == "power_of_attorney":
        _roles = ("Доверитель", "Представитель")
    elif _key.startswith("appeal_") or _scenario.family == "procedural":
        _roles = ("Заявитель и процессуальное положение", "Другая сторона и процессуальное положение")
    else:
        _roles = ("Заявитель", "Адресат")
    _fields = []
    for _field in _scenario.fields:
        if _field.key in {"sender", "recipient"}:
            _role = _roles[0 if _field.key == "sender" else 1]
            _field = replace(_field, label=_role, question=f"{_role}: укажите полное ФИО или наименование. Неизвестные сведения можно вписать позже.")
        if _field.key in {"sender_address", "recipient_address"}:
            _role = _roles[0 if _field.key == "sender_address" else 1]
            _field = replace(_field, label=f"Адрес ({_role.lower()})", question=f"Укажите полный адрес: {_role.lower()}.")
        _fields.append(_field)
    SCENARIOS[_key] = replace(_scenario, fields=tuple(_fields))


# A detailed intake and its document share these exact fields. Conditional
# branches are evaluated by the server, not inferred afresh by the prose editor.
_flood = SCENARIOS['claim_damage_flood']
_common_flood = {f.key: f for f in _flood.fields}
SCENARIOS[_flood.key] = replace(_flood, version=2, fields=(
    _common_flood['sender'], _common_flood['sender_address'],
    field('sender_details', 'Дополнительные реквизиты истца', 'Какие дата и место рождения, идентификатор и контакты истца известны? Неизвестное можно дополнить позже.'),
    _common_flood['recipient'], _common_flood['recipient_address'],
    field('recipient_details', 'Дополнительные реквизиты ответчика', 'Какие дата и место рождения, место работы и идентификатор ответчика известны? Неизвестные сведения не нужно угадывать.'),
    _common_flood['court'],
    field('property_address', 'Адрес повреждённой квартиры', 'По какому полному адресу находится повреждённая квартира? Если это ваш указанный адрес, так и напишите.', 'address'),
    field('property_right', 'Право истца на квартиру и подтверждение', 'На каком основании вам принадлежит или предоставлена повреждённая квартира? Укажите известный подтверждающий документ.'),
    field('flood_date', 'Дата залива', 'Когда произошёл залив квартиры?', 'date'),
    field('source_address', 'Адрес источника залива', 'Из какой квартиры или другого помещения поступила вода? Укажите адрес; можно сослаться на уже указанный адрес ответчика.', 'address'),
    field('source_relation', 'Связь ответчика с источником залива', 'Кем ответчик является по отношению к помещению или оборудованию — собственником, жильцом, управляющей организацией? Укажите, что известно и чем подтверждается.'),
    field('damage_object', 'Повреждённые помещения и имущество', 'Какие комнаты, отделка и вещи повреждены при заливе?'),
    field('facts', 'Причина залива и подтверждающие обстоятельства', 'Что известно о причине залива и какими документами это подтверждается?'),
    field('restoration', 'Состояние восстановления', 'Повреждения уже устранены, устранены частично или ремонт ещё не выполнен?', 'choice', choices=('не восстановлено', 'восстановлено', 'частично восстановлено')),
    field('restoration_costs', 'Выполненный ремонт и расходы', 'Какие восстановительные работы уже выполнены, сколько потрачено на работы и материалы и чем подтверждается оплата?', when_field='restoration', when_values=('восстановлено', 'частично восстановлено')),
    field('restoration_estimate', 'Предстоящие восстановительные расходы', 'Какие работы ещё необходимы и чем подтверждается их стоимость — отчётом оценщика, сметой или другим документом?', when_field='restoration', when_values=('не восстановлено', 'частично восстановлено')),
    _common_flood['amount'],
    field('calculation', 'Расчёт материального ущерба', 'Из каких составляющих складывается сумма ущерба? Можно указать расчёт и реквизиты отчёта оценщика; уже возмещённые суммы нужно учесть.'),
    field('evidence', 'Доказательства обстоятельств и размера ущерба', 'Какие документы подтверждают причину залива и размер ущерба? Укажите известные даты и номера акта, отчёта оценщика и других документов.'),
    _common_flood['pretrial'],
    field('litigation_costs', 'Заявляемые судебные расходы', 'Какие расходы, помимо самого ущерба, хотите взыскать и чем подтверждаются их размер и оплата? Если таких требований нет, ответьте «нет».', optional=True),
    field('expertise', 'Просьба о судебной экспертизе', 'Хотите включить ходатайство о назначении судебной экспертизы? Можно ответить «нет» или попросить пояснение.', 'choice', optional=True, choices=('да', 'нет')),
    field('expertise_details', 'Вопросы для судебной экспертизы', 'Какие обстоятельства нужно установить экспертизой и какие вопросы предлагаете поставить эксперту?', when_field='expertise', when_values=('да',)),
    field('security', 'Обеспечение иска', 'Хотите включить просьбу об обеспечительных мерах? Если нет, ответьте «нет».', 'choice', optional=True, choices=('да', 'нет')),
    field('security_details', 'Меры обеспечения и их обоснование', 'Какую конкретную обеспечительную меру просите применить и какие обстоятельства обосновывают её необходимость?', when_field='security', when_values=('да',)),
    _common_flood['requests'], _common_flood['other_participants'],
    field('copy_status', 'Направление копий иска участникам', 'Копии именно этого иска и отсутствующих у других участников приложений уже направлены или отправка ещё предстоит?', 'choice', choices=('направлены', 'не направлены')),
    field('copy_notice', 'Подтверждение направления копий иска', 'Кому, когда и каким способом направлены копии именно иска и приложений? Укажите подтверждающий документ.', when_field='copy_status', when_values=('направлены',)),
    _common_flood['legal_basis'], _common_flood['fee'], _common_flood['jurisdiction'],
    *ENDING,
))


def field_is_active(spec: Field, fields: dict) -> bool:
    if not spec.when_field:
        return True
    parent = fields.get(spec.when_field, {})
    return parent.get('status') == 'filled' and parent.get('value') in spec.when_values


# Curated form adapters keep the intake alongside the versioned assets rather
# than scattering source-specific questions through the conversation controller.
def _load_form_intakes():
    import json
    from pathlib import Path
    directory = Path(__file__).resolve().parents[1] / 'templates' / 'intake'
    for path in sorted(directory.glob('*.json')):
        data = json.loads(path.read_text(encoding='utf-8'))
        if data['scenario'] not in SCENARIOS:
            if not data.get('title') or not data.get('family'): raise ValueError('Unknown form scenario')
            SCENARIOS[data['scenario']]=Scenario(data['scenario'],data['family'],data['title'],(),version=data['version'])
        original = SCENARIOS[data['scenario']]
        fields = tuple(Field(**{**item, 'when_values': tuple(item.get('when_values', [])), 'choices': tuple(item.get('choices', []))}) for item in data['fields'])
        if len(fields) != len({f.key for f in fields}): raise ValueError('Duplicate form field')
        SCENARIOS[original.key] = replace(original, fields=fields, version=data['version'])


_load_form_intakes()


def render_scenario(scenario: Scenario, fields: dict, text_package: dict | None = None) -> str:
    """Deterministic draft preview. No invented legal citations or default clauses."""
    lines = [scenario.title, ""]
    formatted = {}
    for item in scenario.fields:
        value = fields.get(item.key, {})
        text = value.get("value") if value.get("status") == "filled" else None
        if item.kind == "money" and text:
            from app.services.document_presentation import format_money
            text = format_money(text) + " рублей"
        if item.kind == "date" and text:
            from datetime import date
            text = date.fromisoformat(text).strftime("%d.%m.%Y")
        if text:
            formatted[item.key] = text
        lines.extend((f"{item.label}: {text or '[' + item.label.lower() + ']'}", ""))
    if text_package:
        from app.services.document_template_library import render_text_package, format_template_fields
        return render_text_package(text_package, scenario, fields, format_template_fields(scenario, fields))
    lines.append("Черновая структура. Юридический текст и применимость условий требуют проверки. Это не проверенная форма ГАРАНТа.")
    return "\n".join(lines)
