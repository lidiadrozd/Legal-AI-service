"""Apply the authorized title repair and regenerate the reported local draft."""
import asyncio,json
from pathlib import Path
from types import SimpleNamespace
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.chat import ChatSession
from app.models.document import Document
from app.api.chat import get_chats
from app.api.documents import prepare_interview_file

async def main():
    async with AsyncSessionLocal() as db:
        reported=(await db.execute(select(ChatSession).where(ChatSession.id==175))).scalar_one()
        assert 'диван' in reported.document_workflow.get('request','').casefold()
        owner=reported.user_id
        chats=await get_chats(current_user=SimpleNamespace(id=owner),db=db)
        for chat in chats:
            if chat.id in {175,211,213,215}:print('Title:',chat.id,chat.title,flush=True)
        response=await prepare_interview_file(reported,owner,db)
        stored=(await db.execute(select(Document).where(Document.id==response.document_id,Document.user_id==owner))).scalar_one()
        state=reported.document_workflow
        if state.get('form_review_fields'):raise ValueError('Unverified prose: '+repr(state['form_review_fields']))
        target=Path('/app/tests/document-user-qa/corrected-consumer.docx')
        target.write_bytes(Path(stored.file_path).read_bytes())
        await db.commit()
        print('Regenerated reported draft; unverified prose:',state.get('form_review_fields',[]),flush=True)

if __name__=='__main__':asyncio.run(main())
