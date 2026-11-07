"""Fill native DOCX QA copies with the bundled document Python."""
import sys,types,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
app=types.ModuleType('app');app.__path__=[str(ROOT/'backend/app')];sys.modules['app']=app
services=types.ModuleType('app.services');services.__path__=[str(ROOT/'backend/app/services')];sys.modules['app.services']=services
from app.services.document_scenarios import SCENARIOS
from app.services.document_docx_template import fill_docx_template
from docx import Document
from io import BytesIO

out=ROOT/'backend/tests/complete-forms-qa';count=0
for path in out.glob('*.json'):
    data=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data,dict) or 'state' not in data:continue
    state=data['state'];key=state['scenario']
    content=fill_docx_template(state['text_package'],SCENARIOS[key],data['fields'])
    target=out/(key+'.docx');target.write_bytes(content)
    text='\n'.join(p.text for p in Document(BytesIO(content)).paragraphs)
    (out/(key+'.txt')).write_text(text,encoding='utf-8');count+=1
print('Filled factual DOCX files:',count)
