"""Explicit local repair of the user-reported chat; never logs personal data."""
import asyncio
from pathlib import Path
import re
from copy import deepcopy

from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.chat import ChatSession, Message
from app.models.document import Document
from app.api.documents import interview_file_reply
from app.services.document_workflow import advance_interview, file_request_kind
from app.services.llm_cost import record_llm_usage
from app.core.config import settings
from app.services.document_drafting import facts_digest, narrative_keys, canonical_editorial
from app.services.llm_cost import TokenUsage


async def main():
    async with AsyncSessionLocal() as db:
        chat = (await db.execute(select(ChatSession).where(ChatSession.id == 115).with_for_update())).scalar_one()
        turns = list((await db.execute(select(Message.content).where(Message.chat_id == chat.id, Message.role == 'user')
                                      .order_by(Message.id.asc()))).scalars())
        request = next((t for t in reversed(turns) if file_request_kind(t) == 'create'), None)
        if not request:
            raise RuntimeError('No explicit file request found; no user data changed')
        previous = deepcopy(chat.document_workflow)
        if previous.get('phase') == 'ready' and previous.get('generated_document'):
            state, answer, usage = deepcopy(previous), '', TokenUsage(0, 0, 0, False)
        else:
            state, answer, usage = await advance_interview(chat.document_workflow, request, prior_user_turns=turns)
        # This reported chat contains an explicit distinction between the old
        # contractual deadline and the new demand deadline. Restore both from
        # that exact user statement, without using assistant suggestions.
        from app.services.document_workflow import apply_updates, FieldUpdate
        from app.services.document_scenarios import SCENARIOS
        original = next((t for t in reversed(turns) if re.search('По расписке.*по этой претензии', t, re.I)), None)
        if original:
            dates = list(re.finditer(r'\d{1,2}\s+[а-я]+\s+\d{4}', original, re.I))
            if len(dates) == 2:
                state = apply_updates(state, [FieldUpdate(key='due_date', status='filled', value=dates[0][0], evidence=original),
                    FieldUpdate(key='response_term', status='filled', value=dates[1][0], evidence=original)], original)
        transfer = next((t for t in reversed(turns) if 'Денежные средства' in t and 'наличными деньгами' in t), None)
        if transfer:
            value = transfer[transfer.index('Денежные средства'):]
            state = apply_updates(state, [FieldUpdate(key='transfer', status='filled', value=value, evidence=transfer)], transfer)
        # Phone/email was never an answer to the signature question.
        signature = state['fields'].get('signature', {})
        if re.search(r'@|\+\d|\d{5}', signature.get('value') or ''):
            state['fields']['signature'] = {'status': 'unknown', 'value': None, 'origin': 'requested_draft', 'evidence': request}
        # Repair the earlier year-only overwrite of the known receipt date.
        agreement = state['fields'].get('agreement', {})
        if re.match(r'^20\d\d\s*год', agreement.get('value') or '', re.I):
            receipt = next((t for t in turns if re.match(r'Расписка, заключена \d{1,2} [а-я]+$', t, re.I)), None)
            if receipt:
                year = re.match(r'^20\d\d', agreement['value'])[0]
                agreement.update(value=receipt + ' ' + year + ' года', evidence=receipt + '\n' + agreement.get('evidence', ''), origin='recovered_user_turns')
        year_reply = next((t for t in reversed(turns) if re.match(r'^20\d\d\s*год', t, re.I)), None)
        if year_reply and '20__' in (agreement.get('value') or ''):
            agreement.update(value=agreement['value'].replace('20__', year_reply[:4]),
                             evidence=agreement.get('evidence', '') + '\n' + year_reply,
                             origin='recovered_user_turns')
        # Reuse the already verified editorial text only for unchanged source
        # facts. Changed formal fragments must have an exact canonical rule.
        if previous.get('draft_digest') == facts_digest(previous['fields']):
            edits = {}
            for key in narrative_keys(state):
                source = state['fields'][key]['value']
                canonical = canonical_editorial(key, source, state['scenario'])
                if canonical:
                    edits[key] = canonical
                elif previous['fields'].get(key, {}).get('value') == source and key in previous.get('draft_fields', {}):
                    edits[key] = previous['draft_fields'][key]
            if set(edits) == set(narrative_keys(state)):
                state.update(draft_fields=edits, draft_digest=facts_digest(state['fields']), draft_error=None)
        chat.document_workflow = state
        answer = await interview_file_reply(chat, chat.user_id, db, answer)
        generated = chat.document_workflow.get('generated_document')
        if not generated or '/download)' not in answer:
            from app.api.documents import prepare_interview_file
            try:
                await prepare_interview_file(chat, chat.user_id, db)
            except Exception as exc:
                cause = exc
                for _ in range(4):
                    if isinstance(cause, ValueError) and str(cause).startswith(('Не удалось', 'Официальную', 'Редакция')):
                        print(str(cause), flush=True)
                    if cause.__cause__ is None: break
                    cause = cause.__cause__
            print('REPAIR NOT COMMITTED: file preparation failed', flush=True)
            await db.rollback()
            return
        reply = Message(chat_id=chat.id, role='assistant', content=answer)
        # Update only this repair's earlier artifact notices, not user/model text.
        previous_notices = (await db.execute(select(Message).where(Message.chat_id == chat.id,
                            Message.role == 'assistant', Message.content.like('Документ подготовлен. Скачайте файл ниже.%')))).scalars().all()
        for previous in previous_notices:
            previous.content = answer
        db.add(reply)
        await db.flush()
        await record_llm_usage(db, user_id=chat.user_id, chat_id=chat.id, message_id=reply.id,
                               model=settings.GIGACHAT_MODEL, cached=False, usage=usage, commit=False)
        await db.commit()
        doc = (await db.execute(select(Document).where(Document.id == generated['document_id']))).scalar_one()
        # A local copy makes the file available in this support conversation too.
        out = Path('/app/storage/documents/chat-115-restored.docx')
        out.write_bytes(Path(doc.file_path).read_bytes())
        print('REPAIRED: chat=115 phase=ready downloadable_file=true bytes=' + str(doc.file_size), flush=True)
        print('Fields: ' + str({k: v['status'] for k, v in chat.document_workflow['fields'].items()}), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
