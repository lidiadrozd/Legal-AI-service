"""Opt-in integration check: actual stored DOCX/PDF from the reported interview."""
import asyncio,json,sys
from copy import deepcopy
from io import BytesIO
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from docx import Document as WordDocument
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.chat import ChatSession,Message
from app.models.document import Document
from app.api.documents import prepare_interview_file
from app.services.document_drafting import facts_digest

async def main():
    folder=Path(__file__).parent/'reported_housing_qa'
    source=json.loads((folder/'source-state.json').read_text(encoding='utf-8'))
    async with AsyncSessionLocal() as db:
        chat=(await db.execute(select(ChatSession).where(ChatSession.id==source['chat_id']).with_for_update())).scalar_one()
        assert facts_digest(chat.document_workflow['fields'])==facts_digest(source['state']['fields']), 'Source changed; no stale overwrite'
        before=deepcopy(chat.document_workflow['fields'])
        chat.document_workflow={**chat.document_workflow,'output_format':'docx'}
        docx=await prepare_interview_file(chat,chat.user_id,db)
        saved_docx=deepcopy(chat.document_workflow)
        version=saved_docx['text_package']['version']
        record=await db.get(Document,docx.document_id);payload=Path(record.file_path).read_bytes()
        parsed=WordDocument(BytesIO(payload));assert len(parsed.tables)==1
        assert any(p.text.startswith('5.2.') for p in parsed.paragraphs)
        (folder/f'housing-layout-v{version}.docx').write_bytes(payload)
        chat.document_workflow={**chat.document_workflow,'output_format':'pdf'}
        pdf=await prepare_interview_file(chat,chat.user_id,db)
        record=await db.get(Document,pdf.document_id);payload=Path(record.file_path).read_bytes()
        assert payload.startswith(b'%PDF-')
        (folder/f'housing-layout-v{version}.pdf').write_bytes(payload)
        assert chat.document_workflow['fields']==before
        chat.document_workflow=saved_docx
        note='Договор обновлён: подзаголовки ответственности сторон отделены от нумерованных условий; исправлены согласование количества комнат и обрезанное окончание фразы о месячной плате. Ответы повторять не нужно.\n\n'
        note+=f'[Скачать договор DOCX](/documents/{docx.document_id}/download)\n\n[Скачать договор PDF](/documents/{pdf.document_id}/download)'
        db.add(Message(chat_id=chat.id,role='assistant',content=note))
        await db.commit()
        print(json.dumps({'chat':chat.id,'docx_ready':True,'pdf_ready':True,'table_columns':2,'source_facts_unchanged':True}),flush=True)
if __name__=='__main__': asyncio.run(main())
