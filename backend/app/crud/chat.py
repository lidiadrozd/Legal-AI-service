# backend/app/crud/chat.py
from typing import List
from sqlalchemy.orm import Session
from app.crud.base import CRUDBase
from app.models.chat import Chat, Message
from app.schemas.chat import ChatCreate, MessageCreate

class CRUDChat(CRUDBase[Chat, ChatCreate, ChatCreate]):
    def get_by_user(self, db: Session, *, user_id: int, skip: int = 0, limit: int = 100) -> List[Chat]:
        return (
            db.query(Chat)
            .filter(Chat.user_id == user_id)
            .order_by(Chat.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def create_message(self, db: Session, *, obj_in: MessageCreate, chat_id: int) -> Message:
        db_obj = Message(**obj_in.dict(), chat_id=chat_id)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

chat = CRUDChat(Chat)
