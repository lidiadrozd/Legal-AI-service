"""Upgrade the remaining 38 forms with purpose-specific clauses and DOCX.

Run --manifest-only in the server environment, then author with the bundled
document Python. Existing versions and the housing table layout are preserved.
"""
import json,sys,re,hashlib
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
TEMPLATES=ROOT/'backend/app/templates'
MANIFEST=ROOT/'artifacts/complete-forms-source.json'


def export_manifest():
    sys.path.insert(0,str(ROOT/'backend'))
    from app.services.document_catalog import catalog_forms
    from app.services.document_scenarios import SCENARIOS
    from app.services.document_template_library import load_text_package
    from app.services.document_form_rules import legal_profile
    forms=[]
    for row in catalog_forms():
        key=row['scenario']
        if key in {'claim_alimony_fixed','complaint_labor_agency'}:continue
        scenario=SCENARIOS[key];package=load_text_package(scenario)
        text,urls=legal_profile(key)
        forms.append(dict(key=key,title=scenario.title,family=scenario.family,version=scenario.version,
            fields=[asdict(f) for f in scenario.fields],package=package,normative=text,source_urls=urls))
    MANIFEST.write_text(json.dumps(forms,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Manifest exported:',len(forms))


def copy_native_form(key,old,package):
    """Housing uses an existing two-column signature table and nested lists."""
    from docx import Document
    from docx.oxml.ns import qn
    previous=TEMPLATES/'assets'/old['docx_asset']['template']
    out=TEMPLATES/'assets'/key/f"v{package['version']}"
    out.mkdir(parents=True,exist_ok=False)
    doc=Document(previous)
    for paragraph in doc.paragraphs:
        if paragraph.text.startswith('7.1.'):
            paragraph.add_run(' Договор найма регулируется главой 35 ГК РФ, в том числе статьями 671, 674, 676, 678, 681–683, 687 и 688.')
    template=out/'template.docx';doc.save(template)
    schema=json.loads((TEMPLATES/'assets'/old['docx_asset']['schema']).read_text(encoding='utf-8'))
    schema.update(version=package['version'],blocks_sha256=hashlib.sha256(json.dumps(package['blocks'],ensure_ascii=False,sort_keys=True).encode()).hexdigest())
    metadata=out/'schema.json';metadata.write_text(json.dumps(schema,ensure_ascii=False,indent=2),encoding='utf-8')
    package['docx_asset']={'template':template.relative_to(TEMPLATES/'assets').as_posix(),'template_sha256':hashlib.sha256(template.read_bytes()).hexdigest(),
        'schema':metadata.relative_to(TEMPLATES/'assets').as_posix(),'schema_sha256':hashlib.sha256(metadata.read_bytes()).hexdigest()}
    (TEMPLATES/'documents'/f'{key}.json').write_text(json.dumps(package,ensure_ascii=False,indent=2),encoding='utf-8')


def upgrade(item):
    from complete_form_content import b,section,body_for,PRESERVE,INTAKE_ONLY
    from build_catalog_docx_assets import build
    key=item['key'];old=item['package'];fields={f['key']:f for f in item['fields']}
    def add(key,label,question,kind='text',optional=False):
        fields.setdefault(key,dict(key=key,label=label,question=question,kind=kind,optional=optional))
    add('legal_basis','Правовое обоснование','Правовое обоснование подставляется по нормативным источникам.')
    if 'contacts' in fields:
        fields['contacts'].update(label='Контактные данные',question='Какой телефон или электронную почту указать для связи? Почтовый адрес уже сохранён. Можно ответить «не знаю».',optional=True)
    for name in ('sender','recipient'):
        label=fields[name]['label']
        fields[name]['question']='Какое полное ФИО или наименование у стороны «'+label+'»?'
    if key.startswith('pretense_consumer_'):
        role='Исполнитель' if key.endswith('defective_service') else 'Продавец'
        fields['recipient'].update(label=role,question='Какое полное ФИО или наименование у стороны «'+role+'»?')
    if 'signature' in fields:fields['signature']['question']='Кто подпишет документ от имени стороны «'+fields['sender']['label']+'»: вы лично или представитель? Можно написать «подпишу сам».'
    if 'counterparty_signature' in fields:fields['counterparty_signature']['question']='Кто подпишет документ от имени стороны «'+fields['recipient']['label']+'»? Укажите ФИО и известные полномочия.'
    court='court' in fields
    if key.startswith('claim_'):add('claim_price','Цена иска','Цена иска определяется из заявленных денежных требований; расчёт выполняется отдельно.')
    if key=='order_alimony':add('copy_notice','Направление копий должнику','Направлены ли должнику копии заявления о судебном приказе и приложений? Укажите подтверждение или что отправка ещё предстоит.')
    if court and 'sender_details' not in fields:add('sender_details','Реквизиты заявителя','Какие дату и место рождения, ИНН, СНИЛС или паспортные данные заявителя указываем? Для организации — ИНН и ОГРН; неизвестное можно дополнить позднее.')
    if key in PRESERVE:
        blocks=deepcopy(old['blocks'])
        if key=='contract_housing':
            for block in blocks:
                if block['text'].startswith('7.1.'):
                    block['text']+=' Договор найма регулируется главой 35 ГК РФ, в том числе статьями 671, 674, 676, 678, 681–683, 687 и 688.'
            # The norm is already a fixed paragraph in the preserved native file.
            only={'legal_basis'}
        else:
            only=set(INTAKE_ONLY)&set(fields)
            if not any('{{legal_basis}}' in x['text'] for x in blocks):
                index=next((i for i,x in enumerate(blocks) if x['role'] in {'request','attachments','signature'} or (x['role']=='heading' and x['text']=='Приложения')),len(blocks))
                blocks[index:index]=section('Правовое регулирование','{{legal_basis}}')
            if key=='claim_damage_flood':
                for block in blocks:
                    if block['text'].startswith('{{requests}} Размер возмещения'):
                        block['text']='{{requests}}'
                # The typed operative clause includes the verified principal;
                # it must not be repeated after the completed request sentence.
                only.add('amount')
            # Older headers combined phone, postal address and party details.
            for block in blocks:
                block['text']=block['text'].replace('Контакты: {{contacts}}','{{contacts}}')
            if court and not any('{{sender_details}}' in x['text'] for x in blocks):
                index=next(i for i,x in enumerate(blocks) if x['role']=='title')
                blocks.insert(index,b('{{sender_details}}','addressee','sender_details'))
            if key.startswith('claim_'):
                for block in blocks:block['text']=block['text'].replace('Цена иска: {{amount}}','Цена иска: {{claim_price}}')
    else:
        only=set(INTAKE_ONLY)&set(fields)
        layout=old['layout']
        blocks=[]
        if layout in {'contract','act','authority'}:
            blocks=[b(item['title'],'title'),b('{{place}}                                        {{date}}','place_date') if 'place' in fields else b('Дата: {{date}}','place_date')]
            if key not in {'act_loan_receipt','power_of_attorney'}:
                blocks+=[b(fields['sender']['label']+': {{sender}}\nАдрес: {{sender_address}}','addressee'),
                    b(fields['recipient']['label']+': {{recipient}}\nАдрес: {{recipient_address}}','addressee')]
        else:
            if court:blocks.append(b('В {{court}}','addressee'))
            else:blocks.append(b('{{recipient}}\nАдрес: {{recipient_address}}','addressee'))
            blocks+=[b(fields['sender']['label']+': {{sender}}\nАдрес: {{sender_address}}','addressee')]
            if 'sender_details' in fields:blocks.append(b('{{sender_details}}','addressee','sender_details'))
            if 'contacts' in fields:blocks.append(b('{{contacts}}','addressee','contacts'))
            if court:
                blocks.append(b(fields['recipient']['label']+': {{recipient}}\nАдрес: {{recipient_address}}','addressee'))
                if 'party_details' in fields:blocks.append(b('{{party_details}}','addressee','party_details'))
                if 'other_participants' in fields:blocks.append(b('Другие участники: {{other_participants}}','addressee','other_participants'))
                if 'claim_price' in fields:blocks.append(b('Цена иска: {{claim_price}}','addressee'))
                if 'fee' in fields:blocks.append(b('{{fee}}','addressee'))
            blocks.append(b(item['title'],'title'))
        blocks+=body_for(key)
        used=set(re.findall(r'\{\{([a-z_]+)\}\}','\n'.join(x['text'] for x in blocks)))
        if 'facts' in fields and 'facts' not in used:blocks.append(b('{{facts}}',when='facts'))
        if 'previous_contact' in fields and 'previous_contact' not in used:blocks.append(b('{{previous_contact}}',when='previous_contact'))
        if 'pretrial' in fields:blocks+=[b('Досудебное урегулирование','heading','pretrial'),b('{{pretrial}}',when='pretrial')]
        if 'calculation' in fields:blocks+=[b('Расчёт денежных требований','heading','calculation'),b('{{calculation}}',when='calculation')]
        blocks+=section('Правовое обоснование','{{legal_basis}}')
        if 'requests' in fields:blocks+=[b('На основании изложенного прошу','heading'),b('{{requests}}','request')]
        if key in {'complaint_consumer_agency','complaint_bailiff_superior'}:
            blocks.append(b('Ответ на обращение прошу направить по указанному почтовому адресу заявителя.'))
        if 'payment' in fields:
            if key in {'order_alimony','claim_alimony_share'}:only.add('payment')
            elif key in {'pretense_consumer_late_delivery','pretense_consumer_defective_goods','pretense_consumer_defective_service','claim_consumer'}:
                blocks.append(b('Способ возврата денежных средств: {{payment}}.',when='payment'))
            else:blocks.append(b('Исполнение денежного требования и направление ответа: {{payment}}.',when='payment'))
        if 'response_term' in fields:blocks.append(b('Прошу исполнить требование в следующий срок: {{response_term}}.',when='response_term'))
        if 'contacts' in fields and layout in {'contract','act','authority'}:blocks.append(b('{{contacts}}',when='contacts'))
        blocks+=[b('Приложения','heading'),b('{{attachments}}','attachments')]
        if layout not in {'contract','act','authority'}:blocks.append(b('Дата: {{date}}','place_date'))
        blocks.append(b('Подпись: __________________ / {{signature}} /','signature'))
        if 'counterparty_signature' in fields:blocks.append(b('Подпись второй стороны: __________________ / {{counterparty_signature}} /','signature'))
    # All placeholders and metadata IDs are audited before any file is authored.
    for x in blocks:
        for name in ('when_field','when_value','when_status','when_values'):x.setdefault(name,None)
    used=set(re.findall(r'\{\{([a-z_]+)\}\}','\n'.join(x['text'] for x in blocks)))
    unknown=used-set(fields)
    unused=set(fields)-used-only-{name for name,f in fields.items() if f['kind']=='choice'}
    if unknown or unused:raise ValueError(f'{key}: unknown={sorted(unknown)}, unrendered={sorted(unused)}')
    if '--validate-only' in sys.argv:
        print('Validated',key)
        return
    formats={}
    for name,field in fields.items():
        if name not in used:continue
        contexts=[x for x in blocks if '{{'+name+'}}' in x['text']]
        standalone=all(x['text'].strip()=='{{'+name+'}}' for x in contexts)
        formats[name]='sentence' if standalone else 'phrase'
        if field['kind'] in {'address','date','money','duration','choice'}:formats[name]='auto'
        if name in {'sender','recipient','employer','seller','signature','counterparty_signature','court','case_number','place','sender_details','recipient_details','party_details','principal_details','agent_details','borrower_details','lender_details'}:formats[name]='requisite'
        if name in {'attachments','documents'}:formats[name]='list'
    package=deepcopy(old)
    current=json.loads((TEMPLATES/'documents'/f'{key}.json').read_text(encoding='utf-8'))
    current_intake=TEMPLATES/'intake'/f'{key}.json'
    current_keys={f['key'] for f in json.loads(current_intake.read_text(encoding='utf-8'))['fields']} if current_intake.exists() else set()
    schema_version=max(item['version']+1,(current.get('schema_version') or 1)+(set(fields)!=current_keys))
    package.update(version=max(old['version'],current['version'])+1,schema_version=schema_version,composition='clause_document',blocks=blocks,
        intake_only_fields=sorted(only),field_formats=formats,source_urls=list(dict.fromkeys(old['source_urls']+item['source_urls'])),checked_at='2026-10-27',docx_asset=None)
    # Insert newly introduced requisites beside the relevant party, not after signature.
    ordered=list(fields.values())
    if court and 'sender_details' in fields:
        ordered=[f for f in ordered if f['key']!='sender_details'];index=next(i for i,f in enumerate(ordered) if f['key']=='sender_address')+1
        ordered.insert(index,fields['sender_details'])
    (TEMPLATES/'intake'/f'{key}.json').write_text(json.dumps(dict(scenario=key,title=item['title'],family=item['family'],version=package['schema_version'],fields=ordered),ensure_ascii=False,indent=2),encoding='utf-8')
    if key=='contract_housing':copy_native_form(key,old,package)
    else:build(key,SimpleNamespace(key=key,fields=[SimpleNamespace(**f) for f in ordered]),package)
    print('Authored',key,'v'+str(package['version']))


def main():
    if '--manifest-only' in sys.argv:return export_manifest()
    selected=next((arg.split('=',1)[1].split(',') for arg in sys.argv if arg.startswith('--only=')),None)
    for item in json.loads(MANIFEST.read_text(encoding='utf-8')):
        if selected is None or item['key'] in selected:upgrade(item)
    if '--validate-only' in sys.argv:return
    catalog=TEMPLATES/'catalog40.json';data=json.loads(catalog.read_text(encoding='utf-8'))
    for row in data['forms']:
        package=json.loads((TEMPLATES/'documents'/f"{row['scenario']}.json").read_text(encoding='utf-8'))
        intake=TEMPLATES/'intake'/f"{row['scenario']}.json"
        row['version']=package['version']
        if intake.exists():row['questions']=len(json.loads(intake.read_text(encoding='utf-8'))['fields'])
    data['revision']='2026-10-27';catalog.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
