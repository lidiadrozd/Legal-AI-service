"""Build the non-personal PDF reference with the deployed DOCX converter."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.services.document_scenarios import SCENARIOS
from app.services.document_template_library import load_text_package
from app.services.document_docx_template import fill_docx_template,docx_to_pdf,ASSET_ROOT

scenario=SCENARIOS['contract_housing'];package=load_text_package(scenario)
fields={f.key:{'status':'unknown','value':None} for f in scenario.fields}
fields['deposit']={'status':'filled','value':'да'}
payload=docx_to_pdf(fill_docx_template(package,scenario,fields))
(ASSET_ROOT/package['docx_asset']['template']).with_name('reference.pdf').write_bytes(payload)
print('Stored reference PDF:',len(payload),'bytes')
