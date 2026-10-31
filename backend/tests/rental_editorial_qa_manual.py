"""Replay the synthetic rental case and save factual data for visual QA."""
import asyncio,json
from pathlib import Path
from test_rental_editorial_flow import RENTAL_TURNS
from app.services.document_workflow import new_state,advance_interview
from app.services.document_form_composition import prepare_form_document,form_presentation_fields
from app.services.gigachat_client import get_gigachat_client


async def main():
    state=new_state(RENTAL_TURNS[0][0]);report=[]
    for text,expected in RENTAL_TURNS:
        state,answer,_=await advance_interview(state,text)
        report.append({'next':state['last_questions'],'expected':expected})
        if state.get('provider_failure') or state['last_questions']!=([expected] if expected else []):
            raise RuntimeError('Unexpected rental step: '+repr(report[-1]))
    client=await get_gigachat_client()
    state,usage=await prepare_form_document(state,client)
    out=Path(__file__).parent/'rental-editor-qa';out.mkdir(exist_ok=True)
    (out/'rental-claim.json').write_text(json.dumps({'state':state,'fields':form_presentation_fields(state)},ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'report.json').write_text(json.dumps({'steps':report,'review_fields':state['form_review_fields'],'editor_tokens':usage.total_tokens},ensure_ascii=False,indent=2),encoding='utf-8')
    print('Rental replay:',len(report),'steps; unverified slots:',state['form_review_fields'])


if __name__=='__main__':asyncio.run(main())
