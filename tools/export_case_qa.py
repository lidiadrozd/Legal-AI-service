"""Internal synthetic acceptance artifacts. Never edits a user's document.

Run --facts-only with the server Python, then without it with the bundled
document Python. This keeps server dependencies out of document authoring.
"""
import json,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
OUT=ROOT/'artifacts/case-documents-qa'
OUT.mkdir(parents=True,exist_ok=True)

if '--facts-only' in sys.argv:
    sys.path.insert(0,str(ROOT/'backend/tests'))
    from test_document_case_composition import labor_case,alimony_case
    from app.services.document_case_composition import prepare_case_document,case_presentation_fields
    for source in (labor_case(),alimony_case()):
        state=prepare_case_document(source)
        data=dict(state=state,fields=case_presentation_fields(state))
        (OUT/(state['scenario']+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
else:
    # Import only the pure template modules, avoiding app/__init__.py, whose
    # server route imports require FastAPI and database drivers.
    import types
    app=types.ModuleType('app');app.__path__=[str(ROOT/'backend/app')];sys.modules['app']=app
    services=types.ModuleType('app.services');services.__path__=[str(ROOT/'backend/app/services')];sys.modules['app.services']=services
    from app.services.document_scenarios import SCENARIOS
    from app.services.document_docx_template import fill_docx_template
    for path in OUT.glob('*.json'):
        data=json.loads(path.read_text(encoding='utf-8'));state=data['state']
        output=OUT/(state['scenario']+'.docx')
        output.write_bytes(fill_docx_template(state['text_package'],SCENARIOS[state['scenario']],data['fields']))
        print(output)
