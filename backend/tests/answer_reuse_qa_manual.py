"""Replay the synthetic service-claim regression through the actual editor.

Writes factual JSON for the bundled authoring runtime; never edits a user's
DOCX or publishes a conversation. Reuses the literal test fixture.
"""
import ast,asyncio,json
from pathlib import Path
from app.services.document_workflow import new_state,advance_interview
from app.services.document_form_composition import prepare_form_document,form_presentation_fields
from app.services.gigachat_client import get_gigachat_client


async def main():
    root=Path(__file__).parent
    parsed=ast.parse((root/'test_document_answer_reuse.py').read_text(encoding='utf-8'))
    case=next(x for x in parsed.body if isinstance(x,ast.AsyncFunctionDef))
    assignments={n.targets[0].id:n.value for n in case.body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name)}
    request=ast.literal_eval(assignments['request'])
    turns=assignments['turns'];turns.elts[0].elts[0]=ast.Constant(request)
    values={'request':request,'turns':ast.literal_eval(turns)}
    state=new_state(values['request']);report=[]
    for text,expected in values['turns']:
        state,answer,_=await advance_interview(state,text)
        report.append({'next':state['last_questions'],'expected':expected,'provider_failure':state.get('provider_failure')})
        if state.get('provider_failure') or state['last_questions']!=([expected] if expected else []):
            raise RuntimeError('Unexpected interview cursor: '+repr(report[-1]))
    client=await get_gigachat_client()
    state,usage=await prepare_form_document(state,client)
    out=root/'answer-reuse-qa';out.mkdir(exist_ok=True)
    (out/'service-claim.json').write_text(json.dumps({'state':state,'fields':form_presentation_fields(state)},ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'report.json').write_text(json.dumps({'turns':report,'review_fields':state['form_review_fields'],'tokens':usage.total_tokens},ensure_ascii=False,indent=2),encoding='utf-8')
    print('Replay turns:',len(report),'unverified slots:',state['form_review_fields'])


if __name__=='__main__':asyncio.run(main())
