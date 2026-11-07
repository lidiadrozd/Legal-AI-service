"""Replay the reported fields through real GigaChat using fictional identities."""
import asyncio,json
from pathlib import Path
from copy import deepcopy
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.chat import ChatSession
from app.services.document_drafting import prepare_document_draft,presentation_fields
from app.services.document_template_library import load_text_package
from app.services.document_scenarios import SCENARIOS
from app.services.gigachat_client import get_gigachat_client
from complete_form_cases import make_state

async def main():
    client=await get_gigachat_client()
    consumer=make_state('pretense_consumer_late_delivery')
    async with AsyncSessionLocal() as db:
        chat=(await db.execute(select(ChatSession).where(ChatSession.id==175))).scalar_one()
        source=chat.document_workflow
        consumer['request']=source['request']
        for key in ('purchase','amount','payment_evidence','consumer_status','delivery_due','delivery_status','facts','seller_response','requests','payment','attachments','date'):
            if key in source['fields']:consumer['fields'][key]=deepcopy(source['fields'][key])
    employment=make_state('contract_employment')
    employment['fields']['sender']['value']='МБОУ «Тестовая школа № 1»'
    employment['fields']['amount']['value']='45000.00'
    employment['fields']['payment']['value']='Заработная плата выплачивается 5 и 20 числа каждого месяца банковским переводом.'
    motion=make_state('motion_attach')
    for key,value in {
        'case_subject':'возмещение ущерба в связи с повреждением ноутбука',
        'documents':'Заключение сервисного центра № 7 от 25.10.2026.',
        'relevance':'Заключение подтверждает повреждение ноутбука и стоимость ремонта 15000 рублей.',
        'requests':'Прошу приобщить к делу заключение сервисного центра № 7 от 25.10.2026.',
    }.items():motion['fields'][key]={'status':'filled','value':value,'original':value,'evidence':value}
    out=Path('/app/tests/document-user-qa');out.mkdir(exist_ok=True)
    for name,state in [('consumer',consumer),('employment',employment),('motion',motion)]:
        result,usage=await prepare_document_draft(state,client)
        fields=presentation_fields(result)
        (out/(name+'.json')).write_text(json.dumps({'state':result,'fields':fields,'tokens':usage.total_tokens},ensure_ascii=False,indent=2),encoding='utf-8')
        print(name,'unverified:',result.get('form_review_fields',[]),'tokens:',usage.total_tokens,flush=True)
        if result.get('form_review_fields'):print('review:',json.dumps(result.get('draft_review',{}),ensure_ascii=False),flush=True)

if __name__=='__main__':asyncio.run(main())
