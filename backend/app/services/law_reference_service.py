from sqlalchemy import select, or_
from app.models.chat import ChatSession, Message
from app.models.chat_law_reference import ChatLawReference, LawChangeNorm
from app.services.legal_sources import LegalSource, NormIdentity


async def save_chat_law_references(db, *, user_id, chat_id, user_message_id, assistant_message_id, references):
    if not references:
        return 0
    owner = await db.scalar(select(ChatSession.id).where(ChatSession.id == chat_id,
                                                        ChatSession.user_id == user_id))
    user_message = await db.scalar(select(Message).where(Message.id == user_message_id,
                                   Message.chat_id == chat_id, Message.role == "user"))
    assistant_message = await db.scalar(select(Message).where(Message.id == assistant_message_id,
                                        Message.chat_id == chat_id, Message.role == "assistant"))
    if owner is None or user_message is None or assistant_message is None:
        raise ValueError("Messages do not belong to this user's chat")
    existing = set((await db.execute(select(ChatLawReference.document_key, ChatLawReference.article,
                    ChatLawReference.part, ChatLawReference.point).where(
                    ChatLawReference.assistant_message_id == assistant_message_id))).all())
    from app.services.answer_norms import extract_answer_norms
    direct = {(r["legal_source"].norm, r["citation_text"]): r for r in extract_answer_norms(assistant_message.content)}
    count = 0
    for item in references:
        source = item.get("legal_source")
        if not isinstance(source, LegalSource):
            continue
        # A caller cannot persist a retrieved-but-uncited source.
        if item.get("origin") == "assistant_citation":
            canonical = direct.get((source.norm, item.get("citation_text")))
            if canonical is None:
                continue
            item = canonical
            source = canonical["legal_source"]
        elif f"[Источник {item.get('citation_id')}]" not in assistant_message.content:
            continue
        norm = source.norm
        key = (norm.document_key, norm.article, norm.part, norm.point)
        if key in existing:
            continue
        existing.add(key)
        db.add(ChatLawReference(chat_id=chat_id, user_message_id=user_message_id,
            assistant_message_id=assistant_message_id, document_key=norm.document_key,
            article=norm.article, part=norm.part, point=norm.point,
            source_url=source.source_url, source_revision=source.revision, source_sha256=source.sha256,
            source_text=item["text"], situation_excerpt=user_message.content[:2000]))
        count += 1
    await db.flush()
    return count


async def save_change_norms(db, *, change_id: int, norms: list[NormIdentity]):
    """Only explicit structured identities; never inferred from the amending act number."""
    existing = set((await db.execute(select(LawChangeNorm.document_key, LawChangeNorm.article,
                    LawChangeNorm.part, LawChangeNorm.point).where(LawChangeNorm.change_id == change_id))).all())
    for norm in norms:
        key = (norm.document_key, norm.article, norm.part, norm.point)
        if key not in existing:
            existing.add(key)
            db.add(LawChangeNorm(change_id=change_id, document_key=norm.document_key,
                                 article=norm.article, part=norm.part, point=norm.point))
    await db.flush()


async def find_references_for_change(db, *, change_id: int, user_id: int | None = None):
    """Candidates, not a relevance verdict. Empty scope means the whole parent scope."""
    query = select(ChatLawReference).join(ChatSession, ChatSession.id == ChatLawReference.chat_id).join(
        LawChangeNorm, LawChangeNorm.document_key == ChatLawReference.document_key).where(
        LawChangeNorm.change_id == change_id, ChatSession.user_id.is_not(None))
    for field in ("article", "part", "point"):
        left, right = getattr(LawChangeNorm, field), getattr(ChatLawReference, field)
        query = query.where(or_(left == "", right == "", left == right))
    if user_id is not None:
        query = query.where(ChatSession.user_id == user_id)
    return list((await db.scalars(query.distinct().order_by(ChatLawReference.id))).all())
