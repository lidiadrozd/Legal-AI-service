"""Read-only diagnostics for the reported failed housing export; no identities printed."""
import asyncio
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.chat import ChatSession

async def main():
    async with AsyncSessionLocal() as db:
        chats=(await db.execute(select(ChatSession).order_by(ChatSession.id.desc()).limit(25))).scalars().all()
        for chat in chats:
            state=chat.document_workflow or {}
            if state.get('scenario')!='contract_housing': continue
            print(json.dumps({'chat':chat.id,'phase':state.get('phase'),'draft_error':state.get('draft_error'),
                'draft_cache':list(state.get('draft_cache',{})), 'pending':state.get('last_questions'),
                'fields':{k:{'status':v.get('status'),'length':len(v.get('value') or '')} for k,v in state.get('fields',{}).items()}},ensure_ascii=False))
            if any('Иванова Светлана' in str(f.get('value','')) for f in state.get('fields',{}).values()):
                folder=Path(__file__).parent/'reported_housing_qa';folder.mkdir(exist_ok=True)
                (folder/'source-state.json').write_text(json.dumps({'chat_id':chat.id,'state':state},ensure_ascii=False,indent=2),encoding='utf-8')
                print('Reported state saved for private local reproduction.')
                break
if __name__=='__main__': asyncio.run(main())
