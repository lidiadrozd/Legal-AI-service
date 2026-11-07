"""Explicit operator repair for selected chats; retains old state and user facts."""
import argparse
import asyncio
from copy import deepcopy
import json
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.chat import ChatSession, Message
from app.services.document_workflow import sanitize_interview, advance_interview, file_request_kind, interview_message
from app.api.documents import interview_file_reply

async def main(ids, from_snapshot=False):
    for cid in ids:
        async with AsyncSessionLocal() as db:
            chat = (await db.execute(select(ChatSession).where(ChatSession.id == cid).with_for_update())).scalar_one()
            before = deepcopy(chat.document_workflow)
            if from_snapshot:
                before = deepcopy(before['workflow_repair_snapshot'])
            state = sanitize_interview(before)
            turns = (await db.execute(select(Message.content).where(Message.chat_id == cid, Message.role == 'user').order_by(Message.id))).scalars().all()
            # Reuse the user's existing file request; never invent a request
            # permitting gaps or silently overwrite their supplied facts.
            last = turns[-1] if turns else ''
            if state.get('scenario') != before.get('scenario') and file_request_kind(last):
                state, reply, _ = await advance_interview(state, last, prior_user_turns=list(turns))
            else:
                reply = interview_message(state)
            state.setdefault('workflow_repair_snapshot', before)
            chat.document_workflow = state
            reply = await interview_file_reply(chat, chat.user_id, db, reply)
            previous_reply = (await db.execute(select(Message.content).where(Message.chat_id == cid, Message.role == 'assistant').order_by(Message.id.desc()).limit(1))).scalar_one_or_none()
            if reply != previous_reply: db.add(Message(chat_id=cid, role='assistant', content=reply))
            await db.commit()
            print(json.dumps({'chat_id': cid, 'scenario': chat.document_workflow.get('scenario'),
                'phase': chat.document_workflow.get('phase'), 'questions': chat.document_workflow.get('last_questions'),
                'file': bool(chat.document_workflow.get('generated_document'))}, ensure_ascii=False), flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('ids', type=int, nargs='+')
    parser.add_argument('--from-snapshot', action='store_true')
    args = parser.parse_args()
    asyncio.run(main(args.ids, args.from_snapshot))
