"""Read recent local document diagnostics without changing chats."""
import asyncio,json
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.chat import ChatSession

async def main():
    async with AsyncSessionLocal() as db:
        rows=(await db.execute(select(ChatSession).where(ChatSession.document_workflow.is_not(None)).order_by(ChatSession.id.desc()).limit(7))).scalars().all()
        for row in rows:
            s=row.document_workflow or {}
            print(json.dumps({'id':row.id,'title':row.title,'request':s.get('request'),'scenario':s.get('scenario'),
                'fields':{k:v for k,v in s.get('fields',{}).items() if k in {'delivery_status','seller_response','facts','purchase','delivery_due','payment'}},
                'review':s.get('draft_review'),'unverified':s.get('form_review_fields')},ensure_ascii=False))
asyncio.run(main())
