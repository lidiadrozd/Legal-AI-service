
from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import datetime

# ========================================
# MESSAGE SCHEMAS
# ========================================
class MessageBase(BaseModel):
    """Базовая схема сообщения"""
    model_config = ConfigDict(from_attributes=True)
    
    content: str
    role: str  # "user" or "assistant"

class MessageCreate(MessageBase):
    """Создание сообщения"""
    pass

class Message(MessageBase):
    """Полная схема сообщения"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    chat_id: int
    rating: Optional[str] = None  # "up", "down", null
    created_at: datetime

# ========================================
# CHAT SCHEMAS (УНИКАЛЬНЫЕ ИМЕНА!)
# ========================================
class ChatBase(BaseModel):
    """Базовая схема чата"""
    model_config = ConfigDict(from_attributes=True)
    
    title: Optional[str] = None

class ChatCreate(ChatBase):
    """Создание чата"""
    pass

class ChatResponse(ChatBase):  # ✅ Chat → ChatResponse (без конфликта!)
    """Полная схема чата для ответа"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    user_id: Optional[int] = None
    message_count: int = 0  # Кол-во сообщений
    created_at: datetime
    last_message_at: Optional[datetime] = None

# ========================================
# CHAT LIST RESPONSE
# ========================================
class ChatListResponse(BaseModel):
    """Список чатов"""
    model_config = ConfigDict(from_attributes=True)
    
    chats: List[ChatResponse]
    total: int
    skip: int
    limit: int

# ========================================
# FEEDBACK SCHEMA
# ========================================
class FeedbackCreate(BaseModel):
    """Оценка сообщения"""
    message_id: int
    rating: str  # "up" or "down"

# ========================================
# ЭКСПОРТ (без конфликтов с моделями)
# ========================================
__all__ = [
    "MessageBase", "MessageCreate", "Message",
    "ChatBase", "ChatCreate", "ChatResponse", 
    "ChatListResponse", "FeedbackCreate"
]
