"""Real LibreOffice conversion audit; run in the API container, no user DB writes."""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
import json
from hashlib import sha256
from pypdf import PdfReader
from app.services.document_catalog import catalog_forms
from app.services.document_scenarios import SCENARIOS
from app.services.document_template_library import load_text_package,TEMPLATE_ROOT
from app.services.document_docx_template import fill_docx_template,docx_to_pdf

OUT=Path('/app/tests/catalog40-qa');OUT.mkdir(exist_ok=True)

def audit(row):
    key=row['scenario'];scenario=SCENARIOS[key];package=load_text_package(scenario)
    fields={f.key:{'status':'unknown','value':None} for f in scenario.fields}
    # Known synthetic identities exercise the header/signature, never sources.
    for k,v in dict(sender='Тестова Анна Ивановна',sender_address='г. Екатеринбург, ул. Примерная, д. 10, кв. 5',
        date='2026-10-26',signature='Тестова Анна Ивановна').items():
        if k in fields:fields[k]={'status':'filled','value':v}
    payload=fill_docx_template(package,scenario,fields)
    (OUT/(key+'.docx')).write_bytes(payload)
    pdf=docx_to_pdf(payload);reader=PdfReader(BytesIO(pdf))
    text='\n'.join(p.extract_text() or '' for p in reader.pages)
    assert len(reader.pages)>0 and 'Тестова' in text and '{{' not in text,key
    assert all(abs(float(p.mediabox.width)-595.3)<2 and abs(float(p.mediabox.height)-841.9)<2 for p in reader.pages),key
    assert all(len((p.extract_text() or '').strip())>30 for p in reader.pages),key
    (OUT/(key+'.pdf')).write_bytes(pdf)
    asset_dir=(TEMPLATE_ROOT.parent/'assets'/package['docx_asset']['template']).parent
    (asset_dir/'reference.pdf').write_bytes(pdf)
    return dict(scenario=key,pages=len(reader.pages),docx_sha256=sha256(payload).hexdigest(),pdf_sha256=sha256(pdf).hexdigest())

if __name__=='__main__':
    with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(audit,catalog_forms()))
    (OUT/'report.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Real DOCX/PDF conversions:',len(rows),'pages:',sum(r['pages'] for r in rows))
