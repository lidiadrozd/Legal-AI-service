"""Reproducible catalog audit using synthetic facts; no production DB writes."""
import asyncio,json
from pathlib import Path
from complete_form_cases import make_state
from test_document_case_composition import labor_case,alimony_case
from app.services.document_form_rules import PROFILE_BY_FORM
from app.services.document_form_composition import prepare_form_document,form_presentation_fields
from app.services.document_case_composition import prepare_case_document,case_presentation_fields
from app.services.document_schema import catalog_audit
from app.services.document_quality import quality_issues
from app.services.document_scenarios import SCENARIOS
from app.services.document_template_library import load_text_package

async def main():
    out=Path('/app/tests/catalog-audit-2026-10-29');out.mkdir(exist_ok=True)
    rows=[]
    for key in PROFILE_BY_FORM:
        state,usage=await prepare_form_document(make_state(key),None)
        fields=form_presentation_fields(state)
        (out/(key+'.json')).write_text(json.dumps(dict(state=state,fields=fields),ensure_ascii=False,indent=2),encoding='utf-8')
        rows.append(dict(scenario=key,review_fields=state['form_review_fields'],issues=quality_issues(state)))
    for source in (labor_case(),alimony_case()):
        state=prepare_case_document(source);key=state['scenario']
        (out/(key+'.json')).write_text(json.dumps(dict(state=state,fields=case_presentation_fields(state)),ensure_ascii=False,indent=2),encoding='utf-8')
        rows.append(dict(scenario=key,review_fields=state.get('case_review_fields',[]),issues=quality_issues(state)))
    for key,scenario in SCENARIOS.items():
        if key in {r['scenario'] for r in rows}:continue
        package=load_text_package(scenario)
        fields={f.key:dict(status='unknown',value=None) for f in scenario.fields}
        state=dict(scenario=key,fields=fields,text_package=package)
        (out/(key+'.json')).write_text(json.dumps(dict(state=state,fields=fields),ensure_ascii=False,indent=2),encoding='utf-8')
        rows.append(dict(scenario=key,coverage='legacy_basic',review_fields=[],issues=[]))
    schemas=catalog_audit()
    (out/'report.json').write_text(json.dumps(dict(forms=rows,schemas=schemas),ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(forms=len(rows),schemas=len(schemas),review=[r for r in rows if r['review_fields']],issues=[r for r in rows if r['issues']],schema_errors=[r for r in schemas if r['issues']]),ensure_ascii=False))

if __name__=='__main__':asyncio.run(main())
