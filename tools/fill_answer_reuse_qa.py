"""Author the reviewed synthetic claim with the bundled document runtime."""
import sys,types,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
app=types.ModuleType('app');app.__path__=[str(ROOT/'backend/app')];sys.modules['app']=app
services=types.ModuleType('app.services');services.__path__=[str(ROOT/'backend/app/services')];sys.modules['app.services']=services
from app.services.document_scenarios import SCENARIOS
from app.services.document_docx_template import fill_docx_template
source=ROOT/'backend/tests/answer-reuse-qa/service-claim.json'
data=json.loads(source.read_text(encoding='utf-8'));state=data['state']
out=ROOT/'artifacts/answer-reuse-qa';out.mkdir(exist_ok=True)
target=out/'service-claim.docx'
target.write_bytes(fill_docx_template(state['text_package'],SCENARIOS[state['scenario']],data['fields']))
print(target)
