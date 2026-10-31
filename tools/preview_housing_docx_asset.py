"""Render representative data through the actual template engine for visual QA."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.services.document_scenarios import SCENARIOS
from app.services.document_template_library import load_text_package
from app.services.document_docx_template import fill_docx_template
from app.services.document_drafting import presentation_fields

folder=ROOT/'artifacts/docx-layout-v3';folder.mkdir(exist_ok=True)
scenario=SCENARIOS['contract_housing'];package=load_text_package(scenario)
for name,path in [('housing-short',ROOT/'backend/tests/form_library_qa/contract_housing.json'),
                  ('housing-long',ROOT/'backend/tests/reported_housing_qa/verified-state.json')]:
    payload=json.loads(path.read_text(encoding='utf-8'));state=payload.get('state',payload)
    (folder/(name+'.docx')).write_bytes(fill_docx_template(package,scenario,presentation_fields(state)))
fields={spec.key:{'status':'unknown','value':None} for spec in scenario.fields}
fields['deposit']={'status':'filled','value':'да'}
(folder/'housing-reference.docx').write_bytes(fill_docx_template(package,scenario,fields))
print('Prepared short, long and blank reference DOCX previews')
