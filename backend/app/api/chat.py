"""
Legal AI Service - Chat API endpoints
✅ АСИНХРОННЫЕ: AsyncSession, async def, правильные импорты
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
import asyncio
import traceback
import json
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# ✅ ИСПРАВЛЕННЫЕ ИМПОРТЫ (без конфликтов имен)
from app.db.session import get_db
from app.models.chat import ChatSession, Message
from app.models.law_changes import LawChange
from app.models.user import User
from app.schemas.chat import ChatResponse, MessageCreate, Message as MessageSchema
from app.db.base_class import get_crud
from app.api.deps import get_current_user
from app.services.nlp_service import NLPService

router = APIRouter(prefix="/chat", tags=["💬 Chat"])

_law_change_crud = get_crud(LawChange)
_nlp_service = NLPService()


class SendStreamRequest(BaseModel):
    content: str


@router.post("/new", response_model=ChatResponse)
async def create_chat(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Создать новый чат"""
    from app.models.chat import ChatSession
    
    # Создаем чат напрямую
    new_chat = ChatSession(
        title="Новый чат",
        user_id=current_user.id,
    )
    db.add(new_chat)
    await db.commit()
    await db.refresh(new_chat)
    return ChatResponse.model_validate(new_chat)

@router.get("/list", response_model=List[ChatResponse])
async def get_chats(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Список чатов пользователя"""
    from app.models.chat import ChatSession
    
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == current_user.id)
        .offset(skip)
        .limit(limit)
    )
    chats = result.scalars().all()
    return [ChatResponse.model_validate(chat) for chat in chats]

@router.get("/{chat_id}/history", response_model=List[MessageSchema])
async def get_chat_history(
    chat_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """История сообщений выбранного чата пользователя."""
    chat_result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == chat_id,
            ChatSession.user_id == current_user.id,
        )
    )
    chat_obj = chat_result.scalar_one_or_none()
    if not chat_obj:
        raise HTTPException(status_code=404, detail="Chat not found")

    messages_result = await db.execute(
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(Message.created_at.asc())
    )
    messages = messages_result.scalars().all()
    return [MessageSchema.model_validate(message) for message in messages]

@router.delete("/{chat_id}")
async def delete_chat(
    chat_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Удалить чат пользователя вместе с сообщениями."""
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == chat_id,
            ChatSession.user_id == current_user.id,
        )
    )
    chat_obj = result.scalar_one_or_none()
    if not chat_obj:
        raise HTTPException(status_code=404, detail="Chat not found")

    await db.delete(chat_obj)
    await db.commit()
    return {"message": "Chat deleted"}

@router.post("/{chat_id}/send_stream")
async def send_message_stream(
    chat_id: int,
    message_in: SendStreamRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Стриминговый чат с ИИ-юристом (RAG + GigaChat)
    ✅ АСИНХРОННЫЙ!
    """
    from app.models.chat import ChatSession, Message
    
    async def error_stream(error_text: str):
        yield f"data: {error_text}\n\n"
        yield "data: [DONE]\n\n"

    try:
        # 1. Проверяем доступ к чату
        result = await db.execute(
            select(ChatSession).where(
                ChatSession.id == chat_id,
                ChatSession.user_id == current_user.id
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

        # 4. RAG контекст. Если таблицы/данные пока не готовы, используем fallback.
        context = {"docs": [], "law_db_size": 0}
        try:
            recent_laws = await _law_change_crud.get_multi(db, limit=3)
            context = {
                "docs": [f"Изменение: {law.change_title}" for law in recent_laws],
                "law_db_size": await _law_change_crud.count(db)
            }
        except Exception as context_error:
            # Не валим чат, если контекстный источник временно недоступен.
            print(f"⚠️ RAG context unavailable: {context_error}")
    except HTTPException:
        raise
    except Exception as pre_stream_error:
        traceback.print_exc()
        return StreamingResponse(
            error_stream(f"Ошибка до стриминга: {pre_stream_error}"),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
        )
    
    # 5. Реальный ответ от GigaChat + SSE стриминг
    async def generate_stream():
        try:
            full_response = await _nlp_service.generate_response(
                user_query=message_in.content,
                context=context,
                chat_history=""
            )

            # Стриминг по символам-блокам с сохранением пробелов и переносов
            chunk_size = 24
            for i in range(0, len(full_response), chunk_size):
                part = full_response[i:i + chunk_size]
                chunk = f"data: {json.dumps({'content': part}, ensure_ascii=False)}\n\n"
                yield chunk
                await asyncio.sleep(0.05)

            yield "data: [DONE]\n\n"

            # Обновляем финальный ответ ассистента
            assistant_message.content = full_response
            db.add(assistant_message)
            await db.commit()

        except Exception as e:
            error_text = f"Ошибка GigaChat: {str(e)}"
            assistant_message.content = error_text
            db.add(assistant_message)
            await db.commit()
            yield f"data: {json.dumps({'content': error_text}, ensure_ascii=False)}\n\n"
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
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
