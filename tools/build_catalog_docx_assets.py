"""Offline authoring of complete, versioned DOCX assets for the curated catalog.

Source packages define paragraphs; the model may edit factual fields but cannot
reflow these files, change roles or replace a form by a similar document.
"""
import json,re,sys
from pathlib import Path
from hashlib import sha256
from docx import Document
from docx.shared import Cm,Pt,RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT=Path(__file__).resolve().parents[1]/'backend/app/templates'
sys.path.insert(0,str(ROOT.parents[1]))


def control(tag,child,number):
    node=OxmlElement('w:sdt');pr=OxmlElement('w:sdtPr')
    for key,value in [('tag',tag),('id',str(number))]:
        item=OxmlElement('w:'+key);item.set(qn('w:val'),value);pr.append(item)
    node.append(pr);content=OxmlElement('w:sdtContent');content.append(child);node.append(content)
    return node


def build(key, scenario=None, package=None):
    if scenario is None:
        from app.services.document_scenarios import SCENARIOS
        from app.services.document_template_library import load_text_package
        scenario=SCENARIOS[key];package=load_text_package(scenario)
    if key=='contract_housing' and package.get('composition')!='clause_document': return
    if '--new-version' in sys.argv:package['version']+=1
    out=ROOT/'assets'/key/f"v{package['version']}";out.mkdir(parents=True,exist_ok=True)
    if (out/'template.docx').exists():
        raise ValueError('Existing version is immutable; author with --new-version: '+key)
    doc=Document();sec=doc.sections[0]
    sec.page_width,sec.page_height=Cm(21),Cm(29.7)
    sec.top_margin=sec.bottom_margin=Cm(2);sec.left_margin=Cm(3);sec.right_margin=Cm(1.5)
    for name in ('Normal','Title','Heading 1'):
        style=doc.styles[name];style.font.name='Times New Roman';style.font.size=Pt(12)
        style.font.color.rgb=RGBColor(0,0,0)
        fonts=style.element.get_or_add_rPr().get_or_add_rFonts()
        for attr in list(fonts.attrib):
            if 'theme' in attr.lower(): del fonts.attrib[attr]
        for attr in ('ascii','hAnsi','cs','eastAsia'):fonts.set(qn('w:'+attr),'Times New Roman')
        for border in style.element.findall('.//'+qn('w:pBdr')):border.getparent().remove(border)
    normal=doc.styles['Normal'].paragraph_format
    normal.line_spacing=1.15;normal.space_after=Pt(4);normal.widow_control=True
    normal.first_line_indent=Cm(1.25)
    fields={};conditions={};counter=100
    blocks=list(package['blocks'])
    if package['layout'] in {'act','contract','authority'}:
        blocks=[x for x in blocks if x['role']=='title']+[x for x in blocks if x['role']!='title']
    selectors={};expanded=[]
    for block in blocks:
        selector=block.get('when_field')
        if selector and selector not in selectors:
            selectors[selector]=True
            spec=next(f for f in scenario.fields if f.key==selector)
            if spec.kind=='choice' and not any('{{'+selector+'}}' in x['text'] for x in blocks):
                expanded.append(dict(text=spec.label+': {{'+selector+'}}.',role='body',unknown_selector=selector))
        expanded.append(block)
    for index,block in enumerate(expanded):
        role=block['role'];lines=block['text'].splitlines()
        # Addressee lines are independent right-aligned paragraphs, not one
        # long run or line breaks that Word can rewrap into the body.
        for line in lines:
            p=doc.add_paragraph();pf=p.paragraph_format
            p.alignment=WD_ALIGN_PARAGRAPH.JUSTIFY
            if role in {'title','heading','addressee','place_date','signature','attachments'}:
                pf.first_line_indent=Cm(0)
            if role=='addressee':
                pf.left_indent=Cm(0 if package['layout'] in {'act','contract','authority'} else 8)
                pf.space_after=Pt(2);pf.keep_with_next=True
                p.alignment=WD_ALIGN_PARAGRAPH.LEFT
            elif role=='title':
                p.style=doc.styles['Title']
                p.alignment=WD_ALIGN_PARAGRAPH.CENTER;pf.space_before=Pt(12);pf.space_after=Pt(12);pf.keep_with_next=True
            elif role=='heading':
                p.alignment=WD_ALIGN_PARAGRAPH.LEFT;pf.space_before=Pt(8);pf.keep_with_next=True;pf.keep_together=True
                # Explicit true is also understood by PDF converters which do
                # not consistently retain an empty OOXML on/off element.
                p._p.get_or_add_pPr().find(qn('w:keepNext')).set(qn('w:val'),'1')
            elif role in {'place_date','signature'}:
                p.alignment=WD_ALIGN_PARAGRAPH.LEFT
                pf.keep_with_next=role=='place_date' or index<len(expanded)-1
                if role=='place_date' and '{{place}}' in line and '{{date}}' in line:
                    line=re.sub(r'\}\}[ \t]+\{\{','}}\t{{',line)
                    pf.tab_stops.add_tab_stop(sec.page_width-sec.left_margin-sec.right_margin,WD_TAB_ALIGNMENT.RIGHT)
                    pf.keep_together=True
            elif role=='attachments':pf.keep_with_next=True
            cursor=0
            for match in re.finditer(r'\{\{([a-z_]+)\}\}',line):
                r=p.add_run(line[cursor:match.start()]);r.bold=role in {'title','heading'}
                field=match[1];rule=fields.setdefault(field,{'format':'phrase'})
                if package.get('composition') in {'legal_document','clause_document'} and role in {'request','attachments'}:
                    rule['preserve_list_numbers']=True
                if field=='requests':rule['format']='sentence'
                if line.strip()==match[0] and role in {'body','request','attachments'}:
                    rule['paragraph_lines']=True
                    if role!='attachments':rule['format']='sentence'
                    elif package.get('composition') in {'legal_document','clause_document'}:rule['format']='plain'
                declared=package.get('field_formats',{}).get(field)
                if declared in {'phrase','sentence','requisite'}:rule['format']=declared
                if declared=='list':rule.update(format='plain',paragraph_lines=True,preserve_list_numbers=True)
                run=OxmlElement('w:r');t=OxmlElement('w:t');t.text=match[0];run.append(t)
                counter+=1;p._p.append(control('field:'+field,run,counter));cursor=match.end()
            run=p.add_run(line[cursor:]);run.bold=role in {'title','heading'}
            if role=='title':
                for run in p.runs:run.font.size=Pt(14)
            if block.get('when_field'):
                name=f'branch_{index}';conditions[name]={'field':block['when_field']}
                if block.get('when_value') is not None:conditions[name]['value']=block['when_value']
                if block.get('when_values') is not None:conditions[name]['values']=block['when_values']
                counter+=1;parent=p._p.getparent();position=parent.index(p._p)
                parent.remove(p._p);parent.insert(position,control('if:'+name,p._p,counter))
            elif block.get('unknown_selector'):
                name=f'unknown_{index}';conditions[name]={'field':block['unknown_selector'],'unknown':True}
                counter+=1;parent=p._p.getparent();position=parent.index(p._p)
                parent.remove(p._p);parent.insert(position,control('if:'+name,p._p,counter))
    # Page numbers are a document field, independent of user facts.
    footer=sec.footer.paragraphs[0];footer.alignment=WD_ALIGN_PARAGRAPH.CENTER
    footer.paragraph_format.first_line_indent=Cm(0)
    field=OxmlElement('w:fldSimple');field.set(qn('w:instr'),'PAGE');footer._p.append(field)
    template=out/'template.docx';doc.save(template)
    schema=dict(scenario=key,version=package['version'],engine='ooxml-content-controls-v1',fields=fields,conditions=conditions,
        blocks_sha256=sha256(json.dumps(package['blocks'],ensure_ascii=False,sort_keys=True).encode()).hexdigest(),
        layout=dict(page='A4',font='Times New Roman',font_pt=12,margins_cm=dict(top=2,bottom=2,left=3,right=1.5)),
        review_status='source_checked_draft',lawyer_reviewed=False)
    schema_path=out/'schema.json';schema_path.write_text(json.dumps(schema,ensure_ascii=False,indent=2),encoding='utf-8')
    package['docx_asset']={
        'template':template.relative_to(ROOT/'assets').as_posix(),'template_sha256':sha256(template.read_bytes()).hexdigest(),
        'schema':schema_path.relative_to(ROOT/'assets').as_posix(),'schema_sha256':sha256(schema_path.read_bytes()).hexdigest()}
    (ROOT/'documents'/f'{key}.json').write_text(json.dumps(package,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':
    rows=json.loads((ROOT/'catalog40.json').read_text(encoding='utf-8'))['forms']
    for row in rows:build(row['scenario'])
    for row in rows:
        package=json.loads((ROOT/'documents'/f"{row['scenario']}.json").read_text(encoding='utf-8'))
        row['version']=package['version']
    (ROOT/'catalog40.json').write_text(json.dumps(dict(revision='2026-10-26',forms=rows),ensure_ascii=False,indent=2),encoding='utf-8')
    print('DOCX assets connected:',len(rows))
