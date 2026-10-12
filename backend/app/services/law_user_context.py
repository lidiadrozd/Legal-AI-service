"""Ограниченный контекст ситуации из сообщений самого пользователя."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ChatSession, Message

MAX_CONTEXT_MESSAGES = 20
MAX_CONTEXT_CHARS = 6000


async def load_law_user_context(
    db: AsyncSession, *, user_id: int, chat_id: int | None,
) -> str:
    """Не использует ответы ассистента и сообщения чужих чатов.

    Это заявления пользователя, а не независимо проверенный профиль.
    Сообщения расположены от старых к новым, чтобы были видны уточнения.
    """
    if chat_id is None:
        return ""
    result = await db.execute(
        select(Message.content)
        .join(ChatSession, ChatSession.id == Message.chat_id)
        .where(ChatSession.user_id == user_id, Message.chat_id == chat_id,
               Message.role == "user")
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(MAX_CONTEXT_MESSAGES)
    )
    # Сначала выделяем бюджет для новых сообщений, затем возвращаем хронологию.
    parts: list[str] = []
    remaining = MAX_CONTEXT_CHARS
    for content in result.scalars().all():
        text = (content or "").strip()
        if not text:
            continue
        separator_size = 2 if parts else 0
        budget = remaining - separator_size
        if budget <= 0:
            break
        parts.append(text[-budget:])
        remaining -= len(parts[-1]) + separator_size
        if remaining <= 0:
            break
    return "\n\n".join(reversed(parts))


async def load_reference_user_context(db: AsyncSession, *, user_id: int, reference) -> str:
    """Keep the original question, nearby preceding statements and recent corrections.

    Personal facts come only from the owner's user messages, never the assistant.
    This bounded window can still contain unrelated topics; matching must distinguish them.
    """
    from sqlalchemy import and_, or_
    anchor = await db.scalar(select(Message).join(ChatSession, ChatSession.id == Message.chat_id).where(
        ChatSession.user_id == user_id, Message.chat_id == reference.chat_id,
        Message.id == reference.user_message_id, Message.role == "user"))
    if anchor is None:
        return ""
    before = or_(Message.created_at < anchor.created_at,
                 and_(Message.created_at == anchor.created_at, Message.id <= anchor.id))
    after = or_(Message.created_at > anchor.created_at,
                and_(Message.created_at == anchor.created_at, Message.id > anchor.id))
    base = select(Message).where(Message.chat_id == reference.chat_id, Message.role == "user")
    preceding = list(await db.scalars(base.where(before).order_by(
        Message.created_at.desc(), Message.id.desc()).limit(10)))
    corrections = list(await db.scalars(base.where(after).order_by(
        Message.created_at.desc(), Message.id.desc()).limit(10)))
    anchor_text = (anchor.content or "").strip()[:2000]
    selected = [(anchor.created_at, anchor.id, anchor_text)] if anchor_text else []
    remaining = MAX_CONTEXT_CHARS - len(anchor_text)
    others = sorted((m for m in preceding + corrections if m.id != anchor.id),
                    key=lambda m: (m.created_at, m.id), reverse=True)
    for message in others:
        text = (message.content or "").strip()
        budget = remaining - (2 if selected else 0)
        if budget <= 0:
            break
        if text:
            text = text[-min(budget, 2000):]
            selected.append((message.created_at, message.id, text))
            remaining -= len(text) + (2 if len(selected) > 1 else 0)
    return "\n\n".join(item[2] for item in sorted(selected))
