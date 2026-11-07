"""Synthetic cases through the real editor; no edits to user conversations."""
import asyncio,json
from copy import deepcopy
from pathlib import Path
from app.services.document_workflow import new_state
from app.services.document_scenarios import SCENARIOS
from app.services.document_drafting import prepare_document_draft,presentation_fields
from app.services.document_template_library import load_text_package
from app.services.document_docx_template import fill_docx_template,docx_to_pdf
from app.services.gigachat_client import get_gigachat_client

CASES={
 'complaint_labor_agency':dict(employment='я работал кладовщиком с 1 февраля по 20 октября 2026 года',violation='ну мне не выплатили зп за октябрь 2026, долг 100000 рублей',requests='проверить невыплату зарплаты и принять меры в пределах полномочий инспекции'),
 'motion_restore_term':dict(reasons='я лежал в больнице с 10 по 20 октября 2026 года, поэтому не смог подать документ вовремя',concurrent_action='вместе с заявлением подаю возражения на исполнение судебного приказа',requests='восстановить срок подачи возражений'),
 'claim_alimony_fixed':dict(fixed_grounds='у ответчика нерегулярный доход, он подрабатывает по разовым заказам',maintenance_calculation='на питание ребёнка трачу 15000 рублей в месяц, на одежду 5000 рублей, есть чеки',requests='взыскать алименты в твёрдой денежной сумме 20000 рублей в месяц'),
}

async def main():
    out=Path('/app/tests/catalog40-live');out.mkdir(exist_ok=True);report=[]
    from app.services import document_workflow
    from app.services.document_export_contract import FIELD_REVIEW_PROMPT
    structured=document_workflow._structured
    async def traced(client,system,data,schema,**kwargs):
        response=await structured(client,system,data,schema,**kwargs)
        if system==FIELD_REVIEW_PROMPT:
            (out/(key+'-review.json')).write_text(json.dumps(dict(data=data,result=response.content),ensure_ascii=False,indent=2),encoding='utf-8')
        return response
    document_workflow._structured=traced
    client=await get_gigachat_client()
    chat=client.chat_completion;attempts=[]
    async def traced_chat(messages,*args,**kwargs):
        response=await chat(messages,*args,**kwargs)
        for message in messages:
            if message.get('role')!='user':continue
            try:data=json.loads(message.get('content',''))
            except (ValueError,TypeError):continue
            if data.get('field')=='violation':
                attempts.append(dict(source=data['source_text'],response=response.content))
                (out/'violation-attempts.json').write_text(json.dumps(attempts,ensure_ascii=False,indent=2),encoding='utf-8')
        return response
    client.chat_completion=traced_chat
    for key,values in CASES.items():
        previous=json.loads((out/'report.json').read_text(encoding='utf-8')) if (out/'report.json').exists() else []
        from app.services.document_export_contract import EDITOR_VERSION
        verified=next((r for r in previous if r['scenario']==key and r['status']=='verified' and r.get('editor_version')==EDITOR_VERSION),None)
        if verified:
            report.append(verified);continue
        state=new_state(SCENARIOS[key].title)
        state.update(scenario=key,phase='ready',fields={f.key:{'status':'unknown','value':None} for f in SCENARIOS[key].fields})
        state['fields'].update({k:{'status':'filled','value':v} for k,v in values.items()})
        state['text_package']=load_text_package(SCENARIOS[key]);before=deepcopy(state['fields'])
        partial=out/(key+'-partial.json')
        if partial.exists():
            cached=json.loads(partial.read_text(encoding='utf-8'))
            if cached.get('fields')==state['fields']:state['draft_cache']=cached.get('draft_cache',{})
        try:
            result,usage=await prepare_document_draft(state,client)
            assert state['fields']==before and result['fields']==before
            payload=fill_docx_template(state['text_package'],SCENARIOS[key],presentation_fields(result))
            (out/(key+'.docx')).write_bytes(payload);(out/(key+'.pdf')).write_bytes(await asyncio.to_thread(docx_to_pdf,payload))
            report.append(dict(scenario=key,status='verified',editor_version=EDITOR_VERSION,edited_fields=list(result['draft_fields']),tokens=usage.total_tokens))
        except Exception as exc:
            report.append(dict(scenario=key,status='failed',error_type=type(exc).__name__,fields=getattr(exc,'keys',[]),reason=str(exc)))
            if hasattr(exc,'partial_state'):(out/(key+'-partial.json')).write_text(json.dumps(exc.partial_state,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
    await client.aclose()
    assert all(r['status']=='verified' for r in report)

if __name__=='__main__':asyncio.run(main())
