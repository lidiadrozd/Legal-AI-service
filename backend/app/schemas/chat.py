# backend/app/schemas/chat.py
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class MessageBase(BaseModel):
    content: str
    role: str  # "user" or "assistant"

class MessageCreate(MessageBase):
    pass

class Message(MessageBase):
    id: int
    chat_id: int
    rating: Optional[str] = None  # "up", "down", null
    created_at: datetime

    class Config:
        from_attributes = True

class ChatBase(BaseModel):
    title: Optional[str] = None

class ChatCreate(ChatBase):
    pass

class Chat(ChatBase):
    id: int
    user_id: int
    messages: List[Message] = []
    created_at: datetime

    class Config:
        from_attributes = True
