"""Fill and measure all active curated assets, with exact version/hash records."""
import json,sys,types,hashlib
from pathlib import Path
from zipfile import ZipFile
from lxml import etree
from docx import Document
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
app=types.ModuleType('app');app.__path__=[str(ROOT/'backend/app')];sys.modules['app']=app
services=types.ModuleType('app.services');services.__path__=[str(ROOT/'backend/app/services')];sys.modules['app.services']=services
from app.services.document_scenarios import SCENARIOS
from app.services.document_docx_template import fill_docx_template
from app.services.document_template_library import render_package_blocks,format_template_fields
from app.services.document_workflow_docx import build_legal_docx

SOURCE=ROOT/'backend/tests/catalog-audit-2026-10-29'
OUT=ROOT/'artifacts/catalog-audit-2026-10-29';OUT.mkdir(exist_ok=True,parents=True)
W='http://schemas.openxmlformats.org/wordprocessingml/2006/main';NS={'w':W}
def a(name):return '{'+W+'}'+name
rows=[]
for row in json.loads((SOURCE/'report.json').read_text(encoding='utf-8'))['forms']:
    key=row['scenario'];data=json.loads((SOURCE/(key+'.json')).read_text(encoding='utf-8'))
    state=data['state'];package=state['text_package']
    target=OUT/(key+'.docx')
    if package.get('docx_asset'):payload=fill_docx_template(package,SCENARIOS[key],data['fields'])
    else:
        blocks=render_package_blocks(package,SCENARIOS[key],data['fields'],format_template_fields(SCENARIOS[key],data['fields']))
        payload=build_legal_docx(SCENARIOS[key].title,blocks)
    target.write_bytes(payload)
    doc=Document(target);text='\n'.join(p.text for p in doc.paragraphs)+'\n'+'\n'.join(c.text for t in doc.tables for r in t.rows for c in r.cells)
    (OUT/(key+'.txt')).write_text(text,encoding='utf-8')
    with ZipFile(target) as z:
        root=etree.fromstring(z.read('word/document.xml'))
        sizes=[float(n.get(a('val')))/2 for n in root.findall('.//w:rPr/w:sz',NS)]
        fonts=set(root.xpath('.//w:rFonts/@w:ascii',namespaces=NS))
        tabs=root.xpath('.//w:pPr/w:tabs/w:tab[@w:val="right"]/@w:pos',namespaces=NS)
    sections=[dict(width_cm=round(s.page_width.cm,2),height_cm=round(s.page_height.cm,2),left_cm=round(s.left_margin.cm,2),right_cm=round(s.right_margin.cm,2),top_cm=round(s.top_margin.cm,2),bottom_cm=round(s.bottom_margin.cm,2)) for s in doc.sections]
    findings=[]
    if any(abs(s['width_cm']-21)>.1 or abs(s['height_cm']-29.7)>.1 for s in sections):findings.append('page_not_A4')
    if any(s['left_cm']<2 or s['right_cm']<1 or s['top_cm']<1.5 or s['bottom_cm']<1.5 for s in sections):findings.append('narrow_margin')
    if sizes and min(sizes)<11:findings.append('small_font')
    if '{{' in text or '}}' in text:findings.append('unfilled_control')
    place_line=any(b['role']=='place_date' and '{{place}}' in b['text'] and '{{date}}' in b['text'] for b in package['blocks'])
    if place_line and not tabs:findings.append('no_right_date_tab')
    normal=doc.styles['Normal']
    rows.append(dict(scenario=key,title=SCENARIOS[key].title,coverage=package.get('coverage'),version=package['version'],sha256=hashlib.sha256(target.read_bytes()).hexdigest(),sections=sections,normal_font=normal.font.name,normal_size_pt=normal.font.size.pt if normal.font.size else None,font_sizes=sorted(set(sizes)),fonts=sorted(fonts),date_tab_twips=tabs,findings=findings,source_urls=package.get('source_urls',[]),lawyer_reviewed=False))
(OUT/'layout-report.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(count=len(rows),findings=[r for r in rows if r['findings']]),ensure_ascii=False))
