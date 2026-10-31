"""Fill a test DOCX with the bundled document runtime; original stays intact."""
import sys,types,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
app=types.ModuleType('app');app.__path__=[str(ROOT/'backend/app')];sys.modules['app']=app
services=types.ModuleType('app.services');services.__path__=[str(ROOT/'backend/app/services')];sys.modules['app.services']=services
from app.services.document_scenarios import SCENARIOS
from app.services.document_docx_template import fill_docx_template
data=json.loads((ROOT/'backend/tests/rental-editor-qa/rental-claim.json').read_text(encoding='utf-8'))
out=ROOT/'artifacts/rental-editor-qa';out.mkdir(exist_ok=True)
state=data['state'];target=out/'rental-claim.docx'
target.write_bytes(fill_docx_template(state['text_package'],SCENARIOS[state['scenario']],data['fields']))
print(target)
