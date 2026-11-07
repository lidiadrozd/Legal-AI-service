"""Render tested editorial fields into actual DOCX assets using bundled Python."""
import sys, types, json, argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
app=types.ModuleType('app');app.__path__=[str(ROOT/'backend/app')];sys.modules['app']=app
services=types.ModuleType('app.services');services.__path__=[str(ROOT/'backend/app/services')];sys.modules['app.services']=services
from app.services.document_scenarios import SCENARIOS
from app.services.document_docx_template import fill_docx_template
from docx import Document

parser=argparse.ArgumentParser()
parser.add_argument('--source',default='backend/tests/business-editorial-qa')
parser.add_argument('--output',default='artifacts/business-editorial-qa')
args=parser.parse_args()
out=ROOT/args.output;out.mkdir(parents=True,exist_ok=True)
for source in (ROOT/args.source).glob('*.json'):
    data=json.loads(source.read_text(encoding='utf-8'));state=data['state']
    if state['form_review_fields']:raise ValueError(str(state['form_review_fields']))
    target=out/(source.stem+'.docx')
    target.write_bytes(fill_docx_template(state['text_package'],SCENARIOS[state['scenario']],data['fields']))
    (out/(source.stem+'.txt')).write_text('\n'.join(p.text for p in Document(target).paragraphs),encoding='utf-8')
    print(target)
