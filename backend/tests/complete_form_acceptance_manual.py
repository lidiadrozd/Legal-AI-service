"""Offline/live factual acceptance pass; no user accounts or DB writes."""
import asyncio,json,sys
from pathlib import Path
from complete_form_cases import make_state
from app.services.document_form_rules import PROFILE_BY_FORM
from app.services.document_form_composition import prepare_form_document,form_presentation_fields
from app.services.document_quality import quality_issues

OUT=Path(__file__).parent/'complete-forms-qa'


async def main():
    out=OUT/'live' if '--colloquial' in sys.argv else OUT
    out.mkdir(exist_ok=True,parents=True);client=None;report=[]
    if '--live' in sys.argv:
        from app.services.gigachat_client import get_gigachat_client
        client=await get_gigachat_client()
        if '--trace' in sys.argv:
            chat=client.chat_completion;trace=[]
            async def traced(messages,**kwargs):
                response=await chat(messages,**kwargs)
                trace.append({'function':(kwargs.get('structured_function') or {}).get('name'),'content':response.content})
                (out/'synthetic-trace.json').write_text(json.dumps(trace,ensure_ascii=False,indent=2),encoding='utf-8')
                return response
            client.chat_completion=traced
    selected=next((v.split('=',1)[1].split(',') for v in sys.argv if v.startswith('--only=')),None)
    for key in PROFILE_BY_FORM:
        if selected and key not in selected:continue
        state=make_state(key)
        if '--colloquial' in sys.argv:
            examples={
                'contract_housing':('liability','если наниматель сломает мебель, он оплачивает ремонт'),
                'pretense_debt_loan':('facts','ну знакомый так и не вернул мне 100000 рублей'),
                'motion_postpone':('reasons','ну я лежу в больнице с 9 по 14 ноября 2026 года и поэтому не смогу прийти в суд'),
                'power_of_attorney':('powers','хочу чтобы представитель подавал документы в управляющую компанию и получал ответы')}
            if key in examples:
                field,text=examples[key];state['fields'][field]={'status':'filled','value':text,'original':text,'evidence':text}
        state,usage=await prepare_form_document(state,client)
        fields=form_presentation_fields(state)
        data=dict(state=state,fields=fields)
        (out/(key+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        row=dict(scenario=key,review_fields=state['form_review_fields'],issues=quality_issues(state),tokens=usage.total_tokens)
        report.append(row)
        print(key,'review='+','.join(row['review_fields']),'issues='+','.join(x['code'] for x in row['issues']),flush=True)
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':asyncio.run(main())
