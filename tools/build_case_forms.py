"""Author two complete legal forms using the bundled document runtime.

Intake questions are not document paragraphs. Keep all earlier assets immutable.
"""
import json
from types import SimpleNamespace
from pathlib import Path
from build_catalog_docx_assets import build

ROOT=Path(__file__).resolve().parents[1]/'backend/app/templates'


def block(text,role='body',when=None):
    return dict(text=text,role=role,when_field=when,when_status='filled' if when else None,when_value=None,when_values=None)


def author(key):
    intake_path=ROOT/'intake'/f'{key}.json';path=ROOT/'documents'/f'{key}.json'
    intake=json.loads(intake_path.read_text(encoding='utf-8'));package=json.loads(path.read_text(encoding='utf-8'))
    fields={f['key']:f for f in intake['fields']}
    def change(key,question=None,label=None,kind=None,optional=None):
        field=fields.setdefault(key,dict(key=key,label=label or key,question=question or '',kind=kind or 'text'))
        if question:field['question']=question
        if label:field['label']=label
        if kind:field['kind']=kind
        if optional is not None:field['optional']=optional
    change('contacts','Какой телефон или электронную почту указать для связи? Почтовый адрес уже сохранён. Можно ответить «не знаю».','Контактные данные',optional=True)
    change('signature','Кто подпишет документ: вы лично или представитель? Можно написать «подпишу сам» либо ФИО представителя и его полномочия.')
    change('legal_basis','Правовое обоснование подставляется по проверенным нормативным источникам.','Правовое обоснование')
    if key=='complaint_labor_agency':
        change('sender','Укажите полное ФИО работника, от имени которого подаётся жалоба.')
        change('employment','Какую должность вы занимали и в какой период работали? Номер трудового договора укажите, если он известен.')
        change('dismissal','Когда и по какому основанию вас уволили? Известную дату повторять не нужно — достаточно основания.')
        change('debt_period','За какой период не выплачена заработная плата? Сумму тоже можно указать в этом ответе.')
        change('payment','Куда инспекция должна направить ответ: почтой по вашему адресу, на электронную почту или в личный кабинет?','Получение ответа инспекции')
        change('requests','Какие дополнительные меры просите у инспекции помимо проверки невыплаты зарплаты? Если дополнительных просьб нет, ответьте «нет».')
        blocks=[block('{{recipient}}\nАдрес: {{recipient_address}}','addressee'),
            block('От: {{sender}}\nАдрес: {{sender_address}}','addressee'),block('{{contacts}}','addressee','contacts'),
            block('Жалоба о невыплате заработной платы','title'),
            block('Жалоба подаётся в отношении работодателя {{employer}}. Адрес работодателя или места работы: {{employer_address}}.'),
            block('{{employment}}'),block('{{dismissal}}',when='dismissal'),block('{{debt_period}}'),
            block('{{evidence}}',when='evidence'),block('{{previous_contact}}',when='previous_contact'),block('{{facts}}',when='facts'),
            block('{{legal_basis}}'),block('Прошу','heading'),block('{{requests}}','request'),block('{{payment}}'),
            block('Приложения','heading'),block('{{attachments}}','attachments'),
            block('Дата: {{date}}','place_date'),block('Подпись: __________________ / {{signature}} /','signature')]
        source_urls=['https://www.consultant.ru/document/cons_doc_LAW_34683/274f022222909efcef192f7615b143e34309164f/',
            'https://www.consultant.ru/document/cons_doc_LAW_34683/e1d3302610bfe8a8ec24f33c3029360eeab27635/']
    else:
        change('sender','Укажите полное ФИО родителя, от имени которого подаём иск.')
        change('recipient','Укажите полное ФИО второго родителя, с которого просите взыскать алименты.')
        change('sender_details','Какие дату и место рождения истца, а также его ИНН, СНИЛС или паспортные данные указываем? Неизвестное можно дополнить позднее.','Сведения об истце')
        change('party_details','Какие дата и место рождения, место работы и идентификатор ответчика вам известны? Можно ответить «не знаю».','Сведения об ответчике')
        change('children','Укажите ФИО и дату рождения ребёнка. Если детей несколько, перечислите каждого.')
        change('assistance','Оказывает ли второй родитель помощь ребёнку? Если да, какую и как часто? Расходы на ребёнка — отдельный вопрос.')
        change('maintenance_calculation','Каковы общие ежемесячные расходы на ребёнка и как из них получилась просимая сумма? Например, половина расходов. Можно описать своими словами.')
        change('start','Просите алименты со дня обращения в суд или за более ранний период?')
        change('payment','Способ перечисления можно сообщить позднее, при исполнении решения.','Предпочтение по перечислению',optional=True)
        change('claim_price','Цена иска рассчитывается из суммы платежей за год.','Цена иска')
        change('indexation','Соотношение суммы с прожиточным минимумом для детей требует проверки по региону и дате.','Соотношение с прожиточным минимумом')
        blocks=[block('В {{court}}','addressee'),block('Истец: {{sender}}\nАдрес: {{sender_address}}','addressee'),
            block('{{sender_details}}','addressee','sender_details'),block('{{contacts}}','addressee','contacts'),
            block('Ответчик: {{recipient}}\nАдрес: {{recipient_address}}','addressee'),block('{{party_details}}','addressee','party_details'),
            block('Цена иска: {{claim_price}}','addressee'),block('{{fee}}','addressee'),
            block('Исковое заявление о взыскании алиментов на ребёнка в твёрдой денежной сумме','title'),
            block('{{children}}'),block('{{parentage}}'),block('{{living}}'),block('{{existing_support}}',when='existing_support'),
            block('{{other_dependants}}',when='other_dependants'),block('{{assistance}}',when='assistance'),
            block('{{fixed_grounds}}'),block('{{maintenance_calculation}}'),block('{{legal_basis}}'),
            block('На основании изложенного прошу суд','heading'),block('{{requests}}','request'),
            block('{{indexation}}'),block('Приложения','heading'),block('{{attachments}}','attachments'),
            block('Дата: {{date}}','place_date'),block('Подпись: __________________ / {{signature}} /','signature')]
        source_urls=['https://www.consultant.ru/document/cons_doc_LAW_8982/',
            'https://www.consultant.ru/document/cons_doc_LAW_39570/',
            'https://www.consultant.ru/document/cons_doc_LAW_28165/61fdaaad02ecf7772dc9e0331d21c7ddc3323d4f/']
    # Existing source IDs remain archived and available to the compiler. A
    # field can guide intake without being printed as a disconnected label.
    used=set(__import__('re').findall(r'\{\{([a-z_]+)\}\}','\n'.join(b['text'] for b in blocks)))
    intake['fields']=list(fields.values());intake['version']=4
    package.update(version=package['version']+1,schema_version=4,composition='legal_document',blocks=blocks,
        intake_only_fields=sorted(set(fields)-used),source_urls=source_urls,checked_at='2026-10-26',
        source='Самостоятельная форма с отдельным нормативным и фактическим слоями',docx_asset=None)
    intake_path.write_text(json.dumps(intake,ensure_ascii=False,indent=2),encoding='utf-8')
    # Supply plain schema objects: authoring does not import the server or use
    # its Python environment. Runtime still validates the strict Pydantic form.
    scenario=SimpleNamespace(key=key)
    scenario.fields=[SimpleNamespace(**f) for f in intake['fields']]
    build(key,scenario,package)
    print(key,'version',package['version'])


if __name__=='__main__':
    for key in ('complaint_labor_agency','claim_alimony_fixed'):author(key)
    catalog=ROOT/'catalog40.json';data=json.loads(catalog.read_text(encoding='utf-8'))
    for row in data['forms']:
        package=json.loads((ROOT/'documents'/f"{row['scenario']}.json").read_text(encoding='utf-8'))
        row['version']=package['version']
        intake_path=ROOT/'intake'/f"{row['scenario']}.json"
        if intake_path.exists():row['questions']=len(json.loads(intake_path.read_text(encoding='utf-8'))['fields'])
    catalog.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
