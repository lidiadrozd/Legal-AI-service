"""Author a reusable housing DOCX asset once, never during user export.

Original layout/text; reference downloads are not redistributed as adapters.
Run with the bundled document-authoring Python runtime.
"""
from copy import deepcopy
from hashlib import sha256
import json,re
from pathlib import Path
from docx import Document
from docx.shared import Cm,Pt,RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH,WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT=Path(__file__).resolve().parents[1]/'backend/app/templates'
VERSION=4
OUT=ROOT/f'assets/contract_housing/v{VERSION}'
OUT.mkdir(parents=True,exist_ok=True)
intake=json.loads((ROOT/'intake/contract_housing.json').read_text(encoding='utf-8'))
fields={f['key']:{'format':'sentence'} for f in intake['fields']}
for key in ('sender','recipient','sender_address','recipient_address','property','start_date','term','amount',
            'deposit','deposit_amount','place','date','signature','counterparty_signature'):
    fields[key]['format']='phrase'
for key in ('sender_details','recipient_details'): fields[key]['format']='requisite'
for key, number in dict(property_description='1.2',ownership='1.3',residents='1.4',handover='2.2',
    payment='3.2',utilities='3.3',deposit_terms='3.5',repairs='4.2',access='4.3',
    termination='6.1',return_terms='6.2',additional_terms='7.2').items():
    fields[key]['paragraph_number']=number
fields['liability']['paragraph_section']='5'
fields['liability']['paragraph_headings']=True
fields['attachments']['paragraph_section']='8'
conditions={
    'deposit_yes':{'field':'deposit','value':'да'},'deposit_no':{'field':'deposit','value':'нет'},
    'deposit_unknown':{'field':'deposit','unknown':True},
    'additional':{'field':'additional_terms'},
}
schema=dict(scenario='contract_housing',version=VERSION,engine='ooxml-content-controls-v1',
    fields=fields,conditions=conditions,
    layout=dict(page='A4',margins_cm=dict(top=2.5,bottom=2.5,left=3,right=2),
        font='Times New Roman',font_pt=12,body_first_line_cm=1.25),
    review_status='source_checked_draft',lawyer_reviewed=False)

doc=Document();sec=doc.sections[0]
sec.page_width,sec.page_height=Cm(21),Cm(29.7)
sec.top_margin=sec.bottom_margin=Cm(2.5);sec.left_margin=Cm(3);sec.right_margin=Cm(2)
for name in ('Normal','Title','Heading 1'):
    style=doc.styles[name];style.font.name='Times New Roman';style.font.size=Pt(12)
    style.font.color.rgb=RGBColor(0,0,0)
    fonts=style.element.get_or_add_rPr().get_or_add_rFonts()
    for attr in list(fonts.attrib):
        if 'theme' in attr.lower(): del fonts.attrib[attr]
    for attr in ('ascii','hAnsi','cs','eastAsia'): fonts.set(qn('w:'+attr),'Times New Roman')
    for border in style.element.findall('.//'+qn('w:pBdr')): border.getparent().remove(border)
normal=doc.styles['Normal'].paragraph_format
normal.line_spacing=1.15;normal.space_after=Pt(4);normal.widow_control=True
normal.first_line_indent=Cm(1.25)
doc.styles['Title'].font.size=Pt(14)
blocks=[];used=set();control_id=100

def control(tag,children):
    global control_id
    control_id+=1
    sdt=OxmlElement('w:sdt');pr=OxmlElement('w:sdtPr')
    for name,value in (('tag',tag),('id',str(control_id))):
        item=OxmlElement('w:'+name);item.set(qn('w:val'),value);pr.append(item)
    sdt.append(pr);content=OxmlElement('w:sdtContent')
    for child in children: content.append(child)
    sdt.append(content);return sdt

def fill(p,text):
    cursor=0
    for match in re.finditer(r'\{\{([a-z_]+)\}\}',text):
        p.add_run(text[cursor:match.start()]);key=match[1];used.add(key)
        run=OxmlElement('w:r');t=OxmlElement('w:t');t.text=match[0];run.append(t)
        p._p.append(control('field:'+key,[run]));cursor=match.end()
    p.add_run(text[cursor:])

def para(text,role='body',condition=None,parent=None,style=None):
    p=(parent or doc).add_paragraph(style=style or ('Title' if role=='title' else 'Heading 1' if role=='heading' else 'Normal'))
    fill(p,text)
    p.alignment=WD_ALIGN_PARAGRAPH.JUSTIFY
    pf=p.paragraph_format
    pf.keep_with_next=role in {'title','heading','place_date'}
    if role in {'title','heading','place_date','signature','requisite'}: pf.first_line_indent=Cm(0)
    if role=='title':
        p.alignment=WD_ALIGN_PARAGRAPH.CENTER;pf.space_after=Pt(10)
    if role=='heading':
        pf.space_before=Pt(8);pf.space_after=Pt(4)
    if role=='place_date':
        p.alignment=WD_ALIGN_PARAGRAPH.LEFT;pf.tab_stops.add_tab_stop(Cm(16),WD_TAB_ALIGNMENT.RIGHT)
    for run in p.runs:
        run.bold=role in {'title','heading'}
    if condition:
        node=p._p;container=node.getparent();index=container.index(node)
        container.insert(index,control('if:'+condition,[node]))
    entry={'text':text,'role':role if role!='requisite' else 'body'}
    if condition:
        rule=conditions[condition]
        if not rule.get('unknown'):
            entry.update(when_field=rule['field'])
            entry.update(when_value=rule['value']) if 'value' in rule else entry.update(when_status='filled')
    if parent is None and condition!='deposit_unknown': blocks.append(entry)
    return p

para('Договор найма жилого помещения','title')
para('{{place}}\t{{date}}','place_date')
para('Наймодатель: {{sender}}.')
para('Наниматель: {{recipient}}.')
para('Указанные лица, далее совместно именуемые «Стороны», заключили настоящий договор о нижеследующем.')
para('1. Предмет договора','heading')
para('1.1. Наймодатель предоставляет Нанимателю за плату во владение и пользование для проживания жилое помещение по адресу: {{property}}.')
para('1.2. Характеристики жилого помещения: {{property_description}}')
para('1.3. Основание права или полномочий Наймодателя: {{ownership}}')
para('1.4. Постоянно проживающие совместно с Нанимателем лица: {{residents}}')
para('2. Срок и передача помещения','heading')
para('2.1. Дата начала найма: {{start_date}}. Продолжительность найма: {{term}}.')
para('2.2. Порядок передачи жилого помещения: {{handover}}')
para('3. Плата и расчёты','heading')
para('3.1. Ежемесячная плата за наём составляет {{amount}}.')
para('3.2. Порядок внесения платы: {{payment}}')
para('3.3. Коммунальные и прочие платежи: {{utilities}}')
para('3.4. Обеспечительный платёж не предусмотрен.',condition='deposit_no')
para('3.4. Обеспечительный платёж составляет {{deposit_amount}}.',condition='deposit_yes')
para('3.4. Обеспечительный платёж: {{deposit}}.',condition='deposit_unknown')
para('3.5. Условия внесения, зачёта и возврата обеспечительного платежа: {{deposit_terms}}',condition='deposit_yes')
para('4. Права и обязанности сторон','heading')
para('4.1. Помещение предоставляется для проживания. Наниматель обязан использовать его по назначению, обеспечивать сохранность и своевременно вносить согласованные платежи.')
para('4.2. Условия ремонта и обслуживания: {{repairs}}')
para('4.3. Порядок доступа Наймодателя: {{access}}')
para('5. Ответственность сторон','heading')
para('5.1. {{liability}}')
para('6. Изменение, прекращение и возврат','heading')
para('6.1. {{termination}}')
para('6.2. {{return_terms}}')
para('7. Прочие условия','heading')
para('7.1. Вопросы, не урегулированные настоящим договором, разрешаются в соответствии с применимыми нормами законодательства Российской Федерации. Изменения и дополнения оформляются сторонами в письменной форме.')
para('7.2. Дополнительные согласованные условия: {{additional_terms}}',condition='additional')
para('8. Приложения','heading');para('8.1. {{attachments}}')
para('9. Реквизиты и подписи сторон','heading')
table=doc.add_table(rows=1,cols=2);table.autofit=False
table.columns[0].width=table.columns[1].width=Cm(8)
pr=table.rows[0]._tr.get_or_add_trPr();pr.append(OxmlElement('w:cantSplit'))
borders=OxmlElement('w:tblBorders')
for side in ('top','left','bottom','right','insideH','insideV'):
    edge=OxmlElement('w:'+side);edge.set(qn('w:val'),'nil');borders.append(edge)
table._tbl.tblPr.append(borders)
for cell,role,name,address,details,signature in [
    (table.cell(0,0),'Наймодатель','sender','sender_address','sender_details','signature'),
    (table.cell(0,1),'Наниматель','recipient','recipient_address','recipient_details','counterparty_signature')]:
    first=cell.paragraphs[0];first._element.getparent().remove(first._element)
    para(role,'heading',parent=cell)
    para('{{'+name+'}}','requisite',parent=cell)
    para('Адрес: {{'+address+'}}','requisite',parent=cell)
    para('Реквизиты: {{'+details+'}}','requisite',parent=cell)
    para('Подпись: __________________','signature',parent=cell)
    para('{{'+signature+'}}','requisite',parent=cell)
    for p in cell.paragraphs:
        p.alignment=WD_ALIGN_PARAGRAPH.LEFT;p.paragraph_format.first_line_indent=Cm(0)
        p.paragraph_format.line_spacing=1.05;p.paragraph_format.space_after=Pt(5)
    blocks.append(dict(text=role+': {{'+name+'}}\nАдрес: {{'+address+'}}\nРеквизиты: {{'+details+'}}\nПодпись: __________________ / {{'+signature+'}} /',role='signature'))
footer=sec.footer.paragraphs[0];footer.alignment=WD_ALIGN_PARAGRAPH.CENTER;footer.paragraph_format.first_line_indent=Cm(0)
r=footer.add_run('Проект. Требуется проверка юристом.\n');r.font.size=Pt(9)
page=OxmlElement('w:fldSimple');page.set(qn('w:instr'),'PAGE');footer._p.append(page)
doc.core_properties.title='Договор найма жилого помещения'
doc.core_properties.subject='Версионированная форма с полями для заполнения'
assert used==set(fields),(used^set(fields))
doc.save(OUT/'template.docx')
(OUT/'schema.json').write_text(json.dumps(schema,ensure_ascii=False,indent=2),encoding='utf-8')
package_path=ROOT/'documents/contract_housing.json'
package=json.loads(package_path.read_text(encoding='utf-8'))
package.update(version=VERSION,blocks=blocks,docx_asset=dict(
    template=f'contract_housing/v{VERSION}/template.docx',template_sha256=sha256((OUT/'template.docx').read_bytes()).hexdigest(),
    schema=f'contract_housing/v{VERSION}/schema.json',schema_sha256=sha256((OUT/'schema.json').read_bytes()).hexdigest()))
package_path.write_text(json.dumps(package,ensure_ascii=False,indent=2),encoding='utf-8')
print('Built housing DOCX v'+str(VERSION)+'; fields:',len(fields),'table: 2 signature columns')
