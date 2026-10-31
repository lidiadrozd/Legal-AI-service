"""Read only diagnostics for user-reported local test chats; no auth tokens."""
import asyncio
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.chat import ChatSession, Message


async def main():
    async with AsyncSessionLocal() as db:
        for cid in (95, 97, 99):
            chat = await db.get(ChatSession, cid)
            state = chat.document_workflow if chat else None
            print(cid, {k: state.get(k) for k in ("phase", "scenario", "revision", "last_questions")} if state else None)
            if state:
                print("fields", {key: {"status": value.get("status"), "value": value.get("value")}
                                 for key, value in state.get("fields", {}).items()})
            messages = (await db.execute(select(Message).where(Message.chat_id == cid).order_by(Message.id))).scalars().all()
            print("messages", [(m.id, m.role, str(m.created_at)) for m in messages])


if __name__ == "__main__": asyncio.run(main())
