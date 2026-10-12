"""Real browser check using a disposable local demo account; no model calls."""
import asyncio, json, subprocess
from pathlib import Path
from uuid import uuid4
from playwright.async_api import async_playwright
BACKEND = r"""
import asyncio,json,sys
from uuid import uuid4
from sqlalchemy import delete
from app import models
from app.db.session import AsyncSessionLocal,engine
from app.models.user import User
from app.models.chat import ChatSession,Message
from app.models.notification import Notification
from app.models.law_changes import LawDocument,LawChange
from app.models.law_reference_assessment import LawChangeDelivery
from app.core.security import create_access_token
from app.services.notification_bus import publish_notification
async def main():
 mode=sys.argv[1]
 data=json.loads(sys.argv[2])
 async with AsyncSessionLocal() as db:
  if mode=='seed':
   nonce=uuid4().hex
   u=User(email='browser-check-'+nonce+'@example.invalid',full_name='Проверка уведомлений',hashed_password='!',is_active=True,consent_given=True)
   db.add(u);await db.flush()
   chat=ChatSession(user_id=u.id,title='Контрольный прежний вопрос')
   doc=LawDocument(title='Контрольный документ интерфейса',number='DEMO-'+nonce)
   db.add_all([chat,doc]);await db.flush()
   db.add_all([Message(chat_id=chat.id,role='user',content='Контрольный вопрос об операциях по специальному счету.'),Message(chat_id=chat.id,role='assistant',content='Контрольный прежний ответ. Основание: часть 16 статьи 4 закона 103-ФЗ. [Источник 1]')])
   change=LawChange(document_id=doc.id,change_title='Контрольное уведомление интерфейса',description='Проверка отображения; не новое реальное изменение закона.')
   db.add(change);await db.commit()
   data={'user_id':u.id,'chat_id':chat.id,'change_id':change.id,'document_id':doc.id,'token':create_access_token({'sub':u.email}),'user':{'id':str(u.id),'email':u.email,'full_name':u.full_name,'role':'user','is_active':True,'is_consent_given':True,'created_at':'2026-10-11T00:00:00Z'}}
  elif mode=='publish':
   meta={'chat_id':data['chat_id'],'related_chat_ids':[data['chat_id']],'law_change_id':data['change_id'],'reference_ids':[],'norms':[{'document_key':'ru:103-fz:2009-06-03','article':'4','part':'16','point':''}],'notification_basis':'article_change','personal_relevance_checked':False}
   n=Notification(user_id=data['user_id'],title='LAW_CHANGE#'+str(data['change_id'])+': Контрольное уведомление интерфейса',message='Контрольное уведомление. Изменена норма, использованная в прежнем ответе. Откройте связанный чат. Это проверка интерфейса.',notification_type='law_change',severity='medium',is_read=False)
   db.add(n);await db.flush()
   db.add(LawChangeDelivery(user_id=data['user_id'],change_id=data['change_id'],notification_id=n.id,payload_meta=meta))
   await db.commit()
   publish_notification({'id':n.id,'title':n.title,'message':n.message,'type':'law_change','severity':'medium','meta':meta},user_id=data['user_id'])
   data={'published':True}
  elif mode=='cleanup':
   await db.execute(delete(ChatSession).where(ChatSession.id==data['chat_id'],ChatSession.user_id==data['user_id']))
   await db.execute(delete(User).where(User.id==data['user_id']))
   await db.execute(delete(LawChange).where(LawChange.id==data['change_id']))
   await db.execute(delete(LawDocument).where(LawDocument.id==data['document_id']))
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
 report={'real_backend':True,'synthetic_demo_notification':True}
 try:
  async with async_playwright() as p:
   browser=await p.chromium.launch(channel='msedge',headless=True)
   context=await browser.new_context(viewport={'width':1280,'height':900})
   auth={'state':{'user':data['user'],'accessToken':data['token'],'refreshToken':None,'isConsentGiven':True,'isAuthenticated':True},'version':0}
   await context.add_init_script('localStorage.setItem("ai-lawyer-auth",'+json.dumps(json.dumps(auth))+');localStorage.setItem("ai_lawyer_access_token",'+json.dumps(data['token'])+');')
   page=await context.new_page()
   report['stage']='initial_page'
   await page.goto('http://127.0.0.1:3000/chat',wait_until='domcontentloaded')
   bell=page.get_by_role('button',name='Уведомления',exact=True)
   consent=page.get_by_role('button',name='Принять',exact=True)
   if await consent.is_visible():
    await consent.click()
   report['stage']='open_bell'
   await bell.click()
   await page.get_by_text('Нет уведомлений',exact=True).wait_for()
   report['stage']='publish_notification'
   backend('publish',{k:data[k] for k in ('user_id','chat_id','change_id','document_id')})
   link=page.get_by_role('link',name='Открыть прежний вопрос',exact=True)
   try:
    await link.wait_for(timeout=12000);report['realtime_without_reload']=True
   except Exception:
    report['realtime_without_reload']=False
    report['stage']='rest_fallback'
    await page.reload(wait_until='domcontentloaded');await bell.click()
    try:
     await link.wait_for(timeout=12000)
    except Exception:
     await page.screenshot(path='docs/notification_browser_failure.png')
     raise
   report['stage']='details'
   await page.get_by_text('Подробнее об изменении',exact=True).click()
   await page.screenshot(path='docs/notification_browser_panel.png')
   report['stage']='mobile_panel'
   await page.set_viewport_size({'width':390,'height':844})
   await link.wait_for()
   box=await page.get_by_text('Подробнее об изменении',exact=True).bounding_box()
   assert box and box['y'] >= 0 and box['y']+box['height'] <= 844
   assert box['x'] >= 0 and box['x']+box['width'] <= 390
   report['mobile_panel_inside_viewport']=True
   await page.screenshot(path='docs/notification_browser_mobile.png')
   await page.mouse.click(370,600)
   await link.wait_for(state='hidden')
   report['outside_click_closes_panel']=True
   report['stage']='reopen_bell'
   await bell.click()
   await link.wait_for()
   report['stage']='click_chat_link'
   await link.click()
   await page.wait_for_url('**/chat/'+str(data['chat_id']))
   await page.get_by_text('Контрольный вопрос об операциях по специальному счету.',exact=True).wait_for()
   report['bell_notification_visible']=True
   report['click_opened_previous_chat']=True
   await page.screenshot(path='docs/notification_browser_chat.png')
   await browser.close()
  report['state']='ok'
 except Exception as e:
  report.update(state='error',error_type=type(e).__name__,error_detail=str(e)[:1200])
 finally:
  backend('cleanup',{k:data[k] for k in ('user_id','chat_id','change_id','document_id')})
  report['demo_data_deleted']=True
 Path('docs/notification_browser_check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(report,ensure_ascii=False))
asyncio.run(main())
