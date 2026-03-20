"""
Legal AI Service - Chat API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import asyncio
from fastapi.responses import StreamingResponse

from app.api.deps import get_db, get_current_user
from app.crud.chat import chat
from app.models.user import User
from app.models.chat import Chat, Message
from app.schemas.chat import Chat, MessageCreate, Message
from app.services.nlp_service import NLPService
from app.core.config import settings

router = APIRouter(prefix="/chat", tags=["Chat"])

@router.post("/new", response_model=Chat)
def create_chat(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Создать новый чат"""
    new_chat = chat.create(db, obj_in=ChatCreate(title="Новый чат"))
    new_chat.user_id = current_user.id
    db.commit()
    db.refresh(new_chat)
    return new_chat

@router.get("/list", response_model=List[Chat])
def get_chats(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Список чатов пользователя"""
    return chat.get_by_user(db, user_id=current_user.id, skip=skip, limit=limit)

@router.post("/{chat_id}/send_stream")
async def send_message_stream(
    chat_id: int,
    message_in: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Стриминговый чат с ИИ-юристом (RAG + GigaChat)
    """
    # 1. Проверяем доступ к чату
    chat_obj = db.query(Chat).filter(
        Chat.id == chat_id, 
        Chat.user_id == current_user.id
    ).first()
    if not chat_obj:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    # 2. Сохраняем сообщение пользователя
    user_message = chat.create_message(
        db, obj_in=message_in, chat_id=chat_id
    )
    
    # 3. Создаем пустое сообщение ассистента
    assistant_message_in = MessageCreate(content="", role="assistant")
    assistant_message = chat.create_message(
        db, obj_in=assistant_message_in, chat_id=chat_id
    )
    
    # 4. RAG Контекст (заглушка - добавьте реальный vector store)
    context = {
        "docs": [
            "ст. 421 ГК РФ - свобода договора",
            "ст. 450 ГК РФ - расторжение договора",
            "ст. 4 АПК РФ - претензионный порядок"
        ]
    }
    
    # 5. GigaChat через LangChain
    nlp_service = NLPService()
    
    async def generate_stream():
        try:
            # Генерируем полный ответ
            full_response = await nlp_service.generate_response(
                user_query=message_in.content,
                context=context,
                chat_history="Предыдущие сообщения чата..."
            )
            
            # Симулируем стриминг по словам
            for word in full_response.split():
                chunk = f"data: {word}\n\n"
                yield chunk
                await asyncio.sleep(0.05)  # Реалистичная задержка печати
            
            yield "data: [DONE]\n\n"
            
            # Обновляем сообщение ассистента финальным текстом
            assistant_message.content = full_response
            db.commit()
            
        except Exception as e:
            error_msg = f"data: Ошибка ИИ: {str(e)}\n\n"
            yield error_msg
            yield "data: [DONE]\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"}
    )

@router.post("/feedback")
def submit_feedback(
    message_id: int,
    rating: str,  # "up" or "down"
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Оценка ответа ИИ"""
    message = db.query(Message).filter(Message.id == message_id).first()
    if not message or message.chat.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Message not found")
    
    if rating not in ["up", "down"]:
        raise HTTPException(status_code=400, detail="Rating must be 'up' or 'down'")
    
    message.rating = rating
    db.commit()
    return {"message": f"Feedback '{rating}' submitted successfully"}
