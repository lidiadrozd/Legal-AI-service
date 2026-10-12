"""UI -> live GigaChat -> public DB citation, using a disposable test account."""
import asyncio
import json
import subprocess
from pathlib import Path
from playwright.async_api import async_playwright
BACKEND = r"""
import asyncio,json,sys,re
from uuid import uuid4
from sqlalchemy import select,delete
from app.db.session import AsyncSessionLocal,engine
from app.models.user import User
from app.models.chat import ChatSession,Message
from app.models.chat_law_reference import ChatLawReference
from app.models.llm_usage import LlmUsageEvent
from app.models.notification import Notification
from app.models.user_law_interest import UserLawInterest
from app.core.security import create_access_token
async def main():
 mode,data=sys.argv[1],json.loads(sys.argv[2])
 async with AsyncSessionLocal() as db:
  if mode=='seed':
   nonce=uuid4().hex
   u=User(email='ui-chat-check-'+nonce+'@example.invalid',full_name='Контрольный клиент',hashed_password='!',is_active=True,consent_given=True)
   db.add(u);await db.commit()
   data={'user_id':u.id,'token':create_access_token({'sub':u.email}),'user':{'id':str(u.id),'email':u.email,'full_name':u.full_name,'role':'user','is_active':True,'is_consent_given':True,'created_at':'2026-10-11T00:00:00Z'}}
  elif mode=='inspect':
   chats=list(await db.scalars(select(ChatSession).where(ChatSession.user_id==data['user_id'])))
   ids=[c.id for c in chats]
   answers=list(await db.scalars(select(Message).where(Message.chat_id.in_(ids),Message.role=='assistant')))
   refs=list(await db.scalars(select(ChatLawReference).where(ChatLawReference.chat_id.in_(select(ChatSession.id).where(ChatSession.user_id==data['user_id'])))))
   usage=list(await db.scalars(select(LlmUsageEvent).where(LlmUsageEvent.user_id==data['user_id'])))
   data={'chats_created':len(chats),'assistant_saved':any(bool(a.content.strip()) for a in answers),'model_usage_recorded':bool(usage),'model_cache_used':any(u.cached for u in usage),'saved_references':len(refs),'tk_article_80_saved':any(r.document_key=='ru:197-fz:2001-12-30' and r.article=='80' for r in refs),'references_belong_to_chat':bool(refs) and all(r.chat_id in ids for r in refs),'model_http_statuses':sorted({int(code) for a in answers for code in re.findall(r'GigaChat HTTP (\d{3})',a.content)}),'chat_ids':ids}
  elif mode=='cleanup':
   u=await db.get(User,data['user_id'])
   if not u or not u.email.startswith('ui-chat-check-') or not u.email.endswith('@example.invalid'): raise ValueError('not a disposable account')
   await db.execute(delete(ChatLawReference).where(ChatLawReference.chat_id.in_(select(ChatSession.id).where(ChatSession.user_id==data['user_id']))))
   await db.execute(delete(UserLawInterest).where(UserLawInterest.user_id==data['user_id']))
   await db.execute(delete(LlmUsageEvent).where(LlmUsageEvent.user_id==data['user_id']))
   await db.execute(delete(Notification).where(Notification.user_id==data['user_id']))
   await db.execute(delete(ChatSession).where(ChatSession.user_id==data['user_id']))
   await db.execute(delete(User).where(User.id==data['user_id']))
   await db.commit();data={'deleted':True}
 await engine.dispose()
 print(json.dumps(data,ensure_ascii=False))
asyncio.run(main())
"""

def backend(mode,data):
    result=subprocess.run(['docker','exec','-i','legal_ai_api','python','-',mode,json.dumps(data)],input=BACKEND,text=True,encoding='utf-8',capture_output=True,check=True)
    return json.loads(result.stdout)

async def main():
    data=backend('seed',{})
    report={'real_browser':True,'live_model_requested':True,'public_database':True,'question_contains_article_number':False}
    try:
        async with async_playwright() as p:
            browser=await p.chromium.launch(channel='msedge',headless=True)
            context=await browser.new_context(viewport={'width':1280,'height':900})
            auth={'state':{'user':data['user'],'accessToken':data['token'],'refreshToken':None,'isConsentGiven':True,'isAuthenticated':True},'version':0}
            await context.add_init_script('localStorage.setItem("ai-lawyer-auth",'+json.dumps(json.dumps(auth))+');localStorage.setItem("ai_lawyer_access_token",'+json.dumps(data['token'])+');')
            page=await context.new_page()
            report['stage']='open_chat'
            await page.goto('http://127.0.0.1:3000/chat',wait_until='domcontentloaded')
            consent=page.get_by_role('button',name='Принять использование cookie',exact=True)
            await consent.wait_for(state='visible',timeout=10000)
            await consent.click()
            prompt='Собираюсь уволиться по собственному желанию. За сколько дней нужно предупредить работодателя? Укажите точное основание: закон и статью.'
            textbox=page.get_by_placeholder('Задайте юридический вопрос...',exact=True)
            await textbox.fill(prompt)
            report['stage']='send_normal_question'
            await page.get_by_title('Отправить (Enter)',exact=True).click()
            await page.wait_for_url('**/chat/*',timeout=20000)
            await textbox.wait_for(state='visible')
            await page.wait_for_function('!document.querySelector("textarea").disabled',timeout=120000)
            report['stage']='database_reference'
            for attempt in range(60):
                result=backend('inspect',{'user_id':data['user_id']})
                if result['assistant_saved']: break
                await asyncio.sleep(2)
            report.update({k:v for k,v in result.items() if k!='chat_ids'})
            report['ui_opened_created_chat']=int(page.url.rsplit('/',1)[1]) in result['chat_ids']
            assert report['tk_article_80_saved'] and report['references_belong_to_chat'] and report['model_usage_recorded']
            await page.wait_for_function('!document.querySelector("textarea").disabled',timeout=120000)
            await page.screenshot(path='docs/new_chat_browser_check.png')
            report['state']='ok'
            await browser.close()
    except Exception as exc:
        report.update(state='error',error_type=type(exc).__name__)
        result=backend('inspect',{'user_id':data['user_id']})
        report.update({k:v for k,v in result.items() if k!='chat_ids'})
    finally:
        backend('cleanup',{'user_id':data['user_id']})
        report['demo_data_deleted']=True
    Path('docs/new_chat_browser_check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
    raise SystemExit(0 if report.get('state')=='ok' else 1)

if __name__ == '__main__':
    asyncio.run(main())
