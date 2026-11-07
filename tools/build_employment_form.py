"""Original employment form, with explicit pedagogical branches and no defaults."""
import json
from pathlib import Path
from types import SimpleNamespace
from build_catalog_docx_assets import build

ROOT=Path(__file__).resolve().parents[1]/'backend/app/templates'
KEY='contract_employment'

def main():
    fields=[]
    def field(key,label,question,kind='text',optional=False,**extras):
        fields.append(dict(key=key,label=label,question=question,kind=kind,optional=optional,**extras))
    field('sender','Работодатель','Как называется организация или работодатель?')
    field('sender_address','Адрес работодателя','Укажите адрес работодателя.','address')
    field('sender_details','Реквизиты работодателя и представителя','Укажите ИНН работодателя, ФИО и должность представителя. Неизвестное можно дополнить позже.')
    field('authority_basis','Основание полномочий представителя','Какой документ наделяет представителя работодателя правом подписать договор? Например, устав или доверенность с реквизитами; неизвестное можно дополнить позже.')
    field('recipient','Работник','Какое полное ФИО работника?')
    field('recipient_address','Адрес работника','Какой адрес работника указать?','address')
    field('recipient_details','Документ работника','Укажите реквизиты документа, удостоверяющего личность работника; неизвестное можно вписать позже.')
    field('position','Должность','На какую должность принимают работника?')
    field('workplace','Место работы','Укажите место работы: организацию, подразделение при наличии и адрес рабочего места.')
    field('job_function','Трудовая функция','Какие обязанности будет выполнять работник на этой должности?')
    field('employment_type','Характер занятости','Это основная работа или совместительство?','choice',choices=['основная работа','совместительство'])
    field('start_date','Дата начала работы','Когда работник приступает к работе?','date')
    field('term_type','Срок трудового договора','Договор заключается на неопределённый срок или как срочный?','choice',choices=['на неопределённый срок','срочный'])
    field('fixed_term','Срок и основание срочного договора','Укажите срок или событие окончания и законное основание срочного договора. Без основания срок не предполагается.',when_field='term_type',when_values=['срочный'])
    field('amount','Оклад или ставка заработной платы','Какой размер оклада или ставки до удержания НДФЛ согласован, в рублях?','money')
    field('pay_conditions','Условия оплаты','За какой период и объём работы установлен оклад или ставка? Какие доплаты, надбавки и выплаты согласованы?')
    field('payment','Дни и способ выплаты заработной платы','Какие два дня месяца установлены для выплаты зарплаты и каким способом она выплачивается?')
    field('schedule','Рабочее время и отдых','Каковы продолжительность рабочей недели, рабочие дни, время работы, перерывы и выходные?')
    field('work_conditions','Условия труда на рабочем месте','Какие условия труда и класс по результатам СОУТ указаны для рабочего места? Неизвестное не угадываем.')
    field('compensations','Гарантии и компенсации','Какие гарантии и компенсации согласованы, в том числе при вредных условиях? Если дополнительных нет, ответьте «нет».',optional=True)
    field('is_pedagogue','Педагогическая работа','Работа относится к педагогической деятельности?','choice',choices=['да','нет'])
    field('teaching_load','Отдельная педагогическая нагрузка','Если отдельно согласована педагогическая или учебная нагрузка, укажите её объём и период; если такой отдельной нагрузки нет, ответьте «нет».',optional=True,when_field='is_pedagogue',when_values=['да'])
    field('education_details','Документы об образовании и допуске','Какие документы об образовании и квалификации есть у работника? Указывайте только фактически имеющиеся документы.',when_field='is_pedagogue',when_values=['да'])
    field('leave_context','Тип образовательной организации и характер групп','Какой тип образовательной организации и с какими группами работает сотрудник? Индивидуальные медицинские данные детей не нужны.',when_field='is_pedagogue',when_values=['да'])
    field('vacation','Ежегодный оплачиваемый отпуск','Какова согласованная продолжительность ежегодного оплачиваемого отпуска? Для педагогов необходимо учитывать удлинённый отпуск; точное число дней не угадываем.')
    field('probation','Условие об испытании','Согласовано ли испытание? Если да, укажите срок и условия; если нет, ответьте «нет».',optional=True)
    field('additional_terms','Дополнительные условия','Есть ли дополнительные согласованные условия? Если нет, ответьте «нет».',optional=True)
    field('contacts','Контактные данные сторон','Какие телефон и электронную почту указать для связи? Можно ответить «не знаю».',optional=True)
    field('attachments','Приложения','Какие документы будут приложениями к договору? Если нет, ответьте «нет».',optional=True)
    field('place','Место заключения','В каком городе или населённом пункте будет подписан договор?')
    field('date','Дата договора','Какую дату договора указать?','date')
    field('signature','Представитель работодателя','Кто подпишет договор от работодателя? Укажите ФИО.')
    field('counterparty_signature','Работник подписант','Кто подпишет договор от работника? Можно ответить «работник лично».')
    field('legal_basis','Правовое регулирование','Правовое регулирование подставляется по нормативным источникам.')
    blocks=[]
    def block(text,role='body',**condition):
        if condition.get('when_field') and 'when_value' not in condition:condition['when_status']='filled'
        blocks.append(dict(text=text,role=role,**{'when_field':None,'when_status':None,'when_value':None,'when_values':None,**condition}))
    def heading(text):block(text,'heading')
    block('Трудовой договор','title');block('{{place}}\t{{date}}','place_date')
    block('Работодатель: {{sender}}. Адрес: {{sender_address}}. Реквизиты и представитель: {{sender_details}}.')
    block('Основание полномочий представителя работодателя: {{authority_basis}}.')
    block('Работник: {{recipient}}. Адрес: {{recipient_address}}. Документ, удостоверяющий личность: {{recipient_details}}.')
    block('Работодатель и Работник заключили настоящий трудовой договор о нижеследующем.')
    heading('1 Предмет договора')
    block('Должность Работника: {{position}}. Место работы: {{workplace}}.')
    block('{{job_function}}');block('Характер занятости: {{employment_type}}.')
    block('Работник лично выполняет согласованную трудовую функцию и соблюдает правила внутреннего трудового распорядка. Работодатель предоставляет обусловленную договором работу и обеспечивает условия труда в соответствии с трудовым законодательством.')
    heading('2 Начало работы и срок договора');block('Дата начала работы: {{start_date}}.')
    block('Договор заключён на неопределённый срок.',when_field='term_type',when_value='на неопределённый срок')
    block('Срок и основание срочного договора: {{fixed_term}}.',when_field='term_type',when_value='срочный')
    block('Условие об испытании: {{probation}}.',when_field='probation')
    heading('3 Оплата труда');block('Размер оклада или ставки заработной платы до удержания НДФЛ: {{amount}}.')
    block('{{pay_conditions}}');block('Дни и способ выплаты заработной платы: {{payment}}.')
    block('Заработная плата выплачивается не реже чем каждые полмесяца в сроки, установленные в соответствии с трудовым законодательством.')
    heading('4 Рабочее время и отдых');block('{{schedule}}');block('Условия образовательной деятельности: {{leave_context}}.',when_field='is_pedagogue',when_value='да');block('Ежегодный оплачиваемый отпуск: {{vacation}}.')
    heading('5 Условия труда и гарантии');block('{{work_conditions}}')
    block('{{compensations}}',when_field='compensations')
    block('Работник подлежит обязательному социальному страхованию в соответствии с законодательством Российской Федерации.')
    block('6 Особенности педагогической работы','heading',when_field='is_pedagogue',when_value='да')
    block('Отдельно согласованная педагогическая нагрузка: {{teaching_load}}.',when_field='teaching_load')
    block('{{education_details}}',when_field='is_pedagogue',when_value='да')
    block('Продолжительность рабочего времени, учебная нагрузка и ежегодный удлинённый оплачиваемый отпуск определяются с учётом специальных требований к педагогическим работникам. Норма часов преподавания за ставку не заменяет условия обо всём рабочем времени.',when_field='is_pedagogue',when_value='да')
    heading('Изменение и прекращение договора')
    block('Изменение условий договора оформляется в установленном законом порядке. Основания и порядок прекращения трудового договора определяются трудовым законодательством.')
    block('{{additional_terms}}',when_field='additional_terms')
    heading('Правовое регулирование');block('{{legal_basis}}')
    block('Договор составлен в двух экземплярах, имеющих одинаковую юридическую силу, по одному для каждой стороны.')
    block('{{contacts}}',when_field='contacts');heading('Приложения');block('{{attachments}}','attachments')
    heading('Подписи сторон');block('Работодатель: ______________ / {{signature}} /','signature');block('Работник: ______________ / {{counterparty_signature}} /','signature')
    formats={f['key']:('auto' if f['kind'] in {'money','date','choice','address'} else 'sentence') for f in fields}
    for key in ['sender','recipient','sender_details','recipient_details','authority_basis','signature','counterparty_signature','place']:formats[key]='requisite'
    for key in ['position','workplace','payment','fixed_term','teaching_load','vacation','probation','leave_context']:formats[key]='phrase'
    formats['attachments']='list'
    source=['https://mintrud.gov.ru/ministry/programms/trudotn/dogovor','https://www.consultant.ru/document/cons_doc_LAW_34683/','https://publication.pravo.gov.ru/document/0001202505070004']
    old=ROOT/'documents'/f'{KEY}.json'
    version=json.loads(old.read_text(encoding='utf-8'))['version']+1 if old.exists() else 1
    package=dict(scenario=KEY,composition='clause_document',version=version,schema_version=4,coverage='structured',
        source='Самостоятельная форма трудового договора с отдельными педагогическими условиями',usage_basis='Самостоятельная редакция по трудовому законодательству.',
        review_status='source_checked_draft',checked_at='2026-10-29',reviewed_by=None,reviewed_at=None,layout='contract',
        source_urls=source,limitations=['Неизвестные обязательные условия требуют заполнения; их нельзя считать согласованными.',
        'Учебная нагрузка, срок, испытание и отпуск не устанавливаются автоматически.'],blocks=blocks,field_formats=formats,intake_only_fields=[],docx_asset=None)
    intake=dict(scenario=KEY,title='Трудовой договор',family='contract',version=4,fields=fields)
    (ROOT/'intake'/f'{KEY}.json').write_text(json.dumps(intake,ensure_ascii=False,indent=2),encoding='utf-8')
    build(KEY,SimpleNamespace(key=KEY,fields=[SimpleNamespace(**f) for f in fields]),package)
    path=ROOT/'catalog40.json';catalog=json.loads(path.read_text(encoding='utf-8'))
    if not any(row['scenario']==KEY for row in catalog['forms']):catalog['forms'].append(dict(scenario=KEY,title='Трудовой договор',version=1,questions=len(fields),lawyer_reviewed=False))
    for row in catalog['forms']:
        if row['scenario']==KEY:row.update(version=version,questions=len(fields))
    catalog['revision']='2026-10-29';path.write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()
