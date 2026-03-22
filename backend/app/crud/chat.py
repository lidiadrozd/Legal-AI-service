# backend/app/crud/chat.py
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.base_class import CRUDBase
from app.models.chat import ChatSession, Message
from app.schemas.chat import ChatCreate, MessageCreate

class CRUDChat(CRUDBase[ChatSession, ChatCreate, ChatCreate]):
    async def get_by_user(self, db: AsyncSession, *, user_id: int, skip: int = 0, limit: int = 100) -> List[ChatSession]:
        result = await db.execute(
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(ChatSession.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def create_message(self, db: AsyncSession, *, obj_in: MessageCreate, chat_id: int) -> Message:
        db_obj = Message(**obj_in.model_dump(), chat_id=chat_id)
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

chat = CRUDChat(ChatSession)
