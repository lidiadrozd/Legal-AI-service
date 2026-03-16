# backend/app/api/chat.py - Роутер чата
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.api.deps import get_db, get_current_user
from app.crud.chat import chat
from app.models.user import User
from app.models.chat import Chat
from app.schemas.chat import Chat, MessageCreate, Message

router = APIRouter()

@router.post("/new", response_model=Chat)
def create_chat(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    new_chat = chat.create(db, obj_in=ChatCreate())
    new_chat.user_id = current_user.id
    db.commit()
    db.refresh(new_chat)
    return new_chat

@router.get("/list", response_model=List[Chat])
def get_chats(
    skip: int = 0, limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return chat.get_by_user(db, user_id=current_user.id, skip=skip, limit=limit)

@router.post("/{chat_id}/send_stream")
async def send_message_stream(
    chat_id: int,
    message_in: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Проверяем доступ к чату
    chat_obj = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == current_user.id).first()
    if not chat_obj:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    # Сохраняем сообщение пользователя
    user_message = chat.create_message(db, obj_in=message_in, chat_id=chat_id)
    
    # Создаем пустое сообщение ассистента
    assistant_message_in = MessageCreate(content="", role="assistant")
    assistant_message = chat.create_message(db, obj_in=assistant_message_in, chat_id=chat_id)
    
    # Здесь будет LLM интеграция (GigaChat)
    # Для демонстрации возвращаем простой потоковый ответ
    fake_response = "Здравствуйте! Ваш вопрос: '{}'. По российскому законодательству... (полный анализ будет после интеграции GigaChat)".format(
        message_in.content
    )
    
    # Симуляция стриминга (SSE)
    from fastapi.responses import StreamingResponse
    import asyncio
    
    async def stream_response():
        for chunk in fake_response.split(" "):
            yield f"data: {chunk}\n\n"
            await asyncio.sleep(0.1)
        yield "data: [DONE]\n\n"
    
    return StreamingResponse(stream_response(), media_type="text/plain")

@router.post("/feedback")
def submit_feedback(
    message_id: int,
    rating: str,  # "up" or "down"
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    message = db.query(Message).filter(Message.id == message_id).first()
    if not message or message.chat.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Message not found")
    
    message.rating = rating
    db.commit()
    return {"message": "Feedback submitted"}
