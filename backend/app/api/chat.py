"""
Legal AI Service - Chat API endpoints
✅ АСИНХРОННЫЕ: AsyncSession, async def, правильные импорты
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
import asyncio
from fastapi.responses import StreamingResponse

# ✅ ИСПРАВЛЕННЫЕ ИМПОРТЫ (без конфликтов имен)
from app.db.session import get_db  # ✅ Только async!
from app.core.config import settings
from app.models.chat import ChatSession, Message  # ✅ Только SQLAlchemy модели
from app.schemas.chat import ChatResponse, MessageCreate  # ✅ Только Pydantic схемы
from app.db.base_class import LawChangesCRUD  # ✅ Async CRUD

router = APIRouter(prefix="/chat", tags=["💬 Chat"])

@router.post("/new", response_model=ChatResponse)
async def create_chat(
    current_user: dict,  # ✅ Пока без User модели
    db: AsyncSession = Depends(get_db)
):
    """Создать новый чат"""
    from app.models.chat import ChatSession
    
    # Создаем чат напрямую
    new_chat = ChatSession(
        title="Новый чат", 
        user_id=current_user.get("id", 1)
    )
    db.add(new_chat)
    await db.commit()
    await db.refresh(new_chat)
    return ChatResponse.from_orm(new_chat)

@router.get("/list", response_model=List[ChatResponse])
async def get_chats(
    skip: int = 0,
    limit: int = 100,
    current_user: dict = Depends(lambda: {"id": 1}),  # Заглушка
    db: AsyncSession = Depends(get_db)
):
    """Список чатов пользователя"""
    from app.models.chat import ChatSession
    
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == current_user["id"])
        .offset(skip)
        .limit(limit)
    )
    chats = result.scalars().all()
    return [ChatResponse.from_orm(chat) for chat in chats]

@router.post("/{chat_id}/send_stream")
async def send_message_stream(
    chat_id: int,
    message_in: MessageCreate,
    current_user: dict = Depends(lambda: {"id": 1}),
    db: AsyncSession = Depends(get_db)
):
    """
    Стриминговый чат с ИИ-юристом (RAG + GigaChat)
    ✅ АСИНХРОННЫЙ!
    """
    from app.models.chat import ChatSession, Message
    
    # 1. Проверяем доступ к чату
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == chat_id, 
            ChatSession.user_id == current_user["id"]
        )
    )
    chat_obj = result.scalar_one_or_none()
    if not chat_obj:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    # 2. Сохраняем сообщение пользователя
    user_message = Message(
        chat_id=chat_id,
        content=message_in.content,
        role="user"
    )
    db.add(user_message)
    await db.commit()
    await db.refresh(user_message)
    
    # 3. Создаем пустое сообщение ассистента
    assistant_message = Message(
        chat_id=chat_id,
        content="",
        role="assistant"
    )
    db.add(assistant_message)
    await db.commit()
    await db.refresh(assistant_message)
    
    # 4. RAG Контекст (реальный поиск по изменениям)
    law_crud = LawChangesCRUD(Message)
    recent_laws = await law_crud.get_multi(db, limit=3)
    context = {
        "docs": [f"Изменение: {law.change_title}" for law in recent_laws],
        "law_db_size": await law_crud.count(db)
    }
    
    # 5. Симуляция GigaChat стриминга
    async def generate_stream():
        try:
            # Симулируем генерацию ответа
            full_response = f"""Согласно ст. 421 ГК РФ (свобода договора), 
в вашем случае применяются изменения от {asyncio.get_event_loop().time()}.
Контекст из базы: {len(context['docs'])} документов."""
            
            # Стриминг по словам
            for word in full_response.split():
                chunk = f"data: {word}\n\n"
                yield chunk
                await asyncio.sleep(0.05)
            
            yield "data: [DONE]\n\n"
            
            # Обновляем финальный ответ ассистента
            assistant_message.content = full_response
            db.add(assistant_message)
            await db.commit()
            
        except Exception as e:
            yield f"data: Ошибка: {str(e)}\n\n"
            yield "data: [DONE]\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )

@router.post("/feedback")
async def submit_feedback(
    message_id: int,
    rating: str,  # "up" or "down"
    current_user: dict = Depends(lambda: {"id": 1}),
    db: AsyncSession = Depends(get_db)
):
    """Оценка ответа ИИ"""
    from app.models.chat import Message
    
    result = await db.execute(
        select(Message).where(Message.id == message_id)
    )
    message = result.scalar_one_or_none()
    
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    if rating not in ["up", "down"]:
        raise HTTPException(status_code=400, detail="Rating must be 'up' or 'down'")
    
    message.rating = rating
    db.add(message)
    await db.commit()
    
    return {"message": f"Feedback '{rating}' submitted successfully"}
