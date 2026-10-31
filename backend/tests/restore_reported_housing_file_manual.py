"""Complete this reported export only if its facts have not changed since QA."""
import asyncio,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.chat import ChatSession,Message
from app.models.document import Document
from app.api.documents import interview_file_reply
from app.services.document_drafting import facts_digest

async def main():
    folder=Path(__file__).parent/'reported_housing_qa'
    source=json.loads((folder/'source-state.json').read_text(encoding='utf-8'))
    verified=json.loads((folder/'verified-state.json').read_text(encoding='utf-8'))
    async with AsyncSessionLocal() as db:
        chat=(await db.execute(select(ChatSession).where(ChatSession.id==source['chat_id']).with_for_update())).scalar_one()
        assert facts_digest(chat.document_workflow['fields'])==facts_digest(verified['fields']), 'Facts changed; refusing stale repair'
        chat.document_workflow=verified
        reply=await interview_file_reply(chat,chat.user_id,db,'')
        generated=chat.document_workflow.get('generated_document')
        assert generated and '/download)' in reply, 'Export did not complete; transaction will not commit'
        document=await db.get(Document,generated['document_id'])
        payload=Path(document.file_path).read_bytes()
        assert payload[:2]==b'PK'
        (folder/'restored-housing.docx').write_bytes(payload)
        db.add(Message(chat_id=chat.id,role='assistant',content=reply))
        await db.commit()
        print(json.dumps({'chat_id':chat.id,'file_ready':True,'bytes':len(payload)},ensure_ascii=False),flush=True)
if __name__=='__main__': asyncio.run(main())
