"""
Legal AI Service - Chat API endpoints
✅ АСИНХРОННЫЕ: AsyncSession, async def, правильные импорты
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Any, List, Optional, Tuple
import asyncio
import traceback
import json
from pathlib import Path
from uuid import uuid4
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import re

# ✅ ИСПРАВЛЕННЫЕ ИМПОРТЫ (без конфликтов имен)
from app.db.session import get_db, AsyncSessionLocal
from app.models.chat import ChatSession, Message
from app.models.document import Document as StoredDocument
from app.models.law_changes import LawChange
from app.models.user import User
from app.schemas.chat import ChatResponse, MessageCreate, Message as MessageSchema
from app.db.base_class import get_crud
from app.api.deps import get_current_user
from app.services.nlp_service import NLPService
from app.services.document_generation import DocumentGenerationService
from app.services.builtin_templates import (
    BUILTIN_PREFIX,
    list_builtin_templates,
    resolve_builtin_template_path,
)
from app.core.config import settings
from app.utils.text import capitalize_filename, capitalize_first_letter

router = APIRouter(prefix="/chat", tags=["💬 Chat"])

_law_change_crud = get_crud(LawChange)
_nlp_service = NLPService()
_doc_gen = DocumentGenerationService()


def _documents_storage_root() -> Path:
    root = Path(settings.DOCUMENTS_STORAGE_PATH)
    if not root.is_absolute():
        root = Path.cwd() / root
    return root


def _build_chat_context_text(
    law_lines: list[str],
    law_db_size: int,
    template_rows: list[tuple[str, str]],
) -> str:
    parts: list[str] = []
    if law_lines:
        parts.append(
            "Изменения в законодательстве (кратко):\n"
            + "\n".join(f"• {line}" for line in law_lines)
        )
    parts.append(f"Записей в справочнике изменений законов: {law_db_size}")
    if template_rows:
        lines = [
            "Доступные шаблоны (встроенные сервиса и ваши файлы). "
            "В [AUTO_DOC] поле template_title — точное имя файла из списка:",
        ]
        for doc_id, title in template_rows:
            lines.append(f"  • {title}  (id: {doc_id})")
        parts.append("\n".join(lines))
    else:
        parts.append("Шаблоны документов: нет ни встроенных, ни загруженных вами.")
    return "\n\n".join(parts)


async def _persist_assistant_message(message_id: int, content: str) -> None:
    """Сохранить ответ ассистента отдельной сессией: при обрыве SSE запросная сессия может не закоммитить."""
    text = content if content is not None else ""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Message).where(Message.id == message_id))
        row = result.scalar_one_or_none()
        if row is None:
            return
        row.content = text
        session.add(row)
        await session.commit()


def _extract_auto_doc_block(full_response: str) -> tuple[str, Optional[dict[str, Any]]]:
    if not full_response:
        return full_response, None
    marker = "[AUTO_DOC]"
    idx = full_response.rfind(marker)
    if idx == -1:
        return full_response, None
    tail = full_response[idx + len(marker) :].strip()
    if not tail.startswith("{"):
        return full_response, None
    try:
        obj, _end = json.JSONDecoder().raw_decode(tail)
    except json.JSONDecodeError:
        return full_response, None
    if not isinstance(obj, dict):
        return full_response, None
    visible = full_response[:idx].rstrip()
    return visible, obj


def _pick_template_for_auto_doc(
    rows: list[tuple[str, str]],
    template_title: Optional[str],
    document_type: str,
) -> Optional[str]:
    if not rows:
        return None
    tt = (template_title or "").strip().lower()
    if tt:
        for doc_id, title in rows:
            tl = title.lower()
            if tl == tt or tt in tl or tl in tt:
                return doc_id
    dt = (document_type or "").lower()
    keyword_map: list[tuple[str, list[str]]] = [
        ("претенз", ["претенз", "претензия"]),
        ("иск", ["иск", "исков", "исковое"]),
        ("заявлен", ["заявлен", "заявление"]),
        ("договор", ["договор", "соглашен"]),
        ("жалоб", ["жалоб"]),
    ]
    keywords: list[str] = []
    for needle, words in keyword_map:
        if needle in dt:
            keywords.extend(words)
    best_id: Optional[str] = None
    best_score = 0
    for doc_id, title in rows:
        tl = title.lower()
        score = sum(1 for k in keywords if k in tl)
        if score > best_score:
            best_score = score
            best_id = doc_id
    if best_score > 0:
        return best_id
    return rows[0][0]


async def _try_auto_generate_document(
    user: User,
    *,
    spec: dict[str, Any],
    template_rows: list[tuple[str, str]],
    user_query: str,
    chat_history: str,
) -> Optional[StoredDocument]:
    """
    Отдельная сессия БД: стриминг чата может долго держать соединение; коммиты документа — независимо.
    """
    if not (settings.GIGACHAT_CLIENT_ID and settings.GIGACHAT_CLIENT_SECRET):
        return None
    document_type = str(spec.get("document_type") or "").strip() or "Документ"
    raw_tt = spec.get("template_title")
    template_title = str(raw_tt).strip() if raw_tt is not None else None

    template_path: Optional[str] = None
    template_display_name = "без шаблона"
    template_id: Optional[str] = None
    if template_rows:
        template_id = _pick_template_for_auto_doc(template_rows, template_title, document_type)

    async with AsyncSessionLocal() as db:
        if template_id:
            if template_id.startswith(BUILTIN_PREFIX):
                pth, fname = resolve_builtin_template_path(template_id)
                if pth and fname:
                    template_path = pth
                    template_display_name = fname
                else:
                    template_path = None
                    template_display_name = "без шаблона"
            else:
                tpl_result = await db.execute(
                    select(StoredDocument).where(
                        StoredDocument.id == template_id,
                        StoredDocument.user_id == user.id,
                    )
                )
                template_doc = tpl_result.scalar_one_or_none()
                if template_doc and template_doc.file_path:
                    template_path = template_doc.file_path
                    template_display_name = template_doc.title

        output_dir = str(_documents_storage_root() / str(user.id) / "generated")
        doc_id = str(uuid4())
        combined_q = (user_query or "").strip()
        hist = (chat_history or "").strip()
        if hist:
            combined_q = f"{combined_q}\n\nКонтекст диалога:\n{hist[-4500:]}"

        new_doc = StoredDocument(
            id=doc_id,
            user_id=user.id,
            title=capitalize_first_letter(document_type),
            type="generated",
            status="processing",
            file_path=None,
            file_size=None,
            mime_type=None,
        )
        db.add(new_doc)
        await db.commit()
        await db.refresh(new_doc)

        try:
            result = await _doc_gen.generate_document_files(
                user_query=combined_q[:2000],
                document_type=document_type,
                template_name=template_display_name,
                template_path=template_path,
                output_format="docx",
                client_data={},
                output_dir=output_dir,
            )
            new_doc.file_path = result["file_path"]
            new_doc.file_size = result["file_size"]
            new_doc.mime_type = result["mime_type"]
            raw_title = result.get("title") or f"{document_type}.docx"
            new_doc.title = capitalize_filename(Path(str(raw_title)).name)
            new_doc.status = "ready"
            db.add(new_doc)
            await db.commit()
            await db.refresh(new_doc)
            return new_doc
        except Exception as gen_exc:
            new_doc.status = "error"
            db.add(new_doc)
            await db.commit()
            print(f"[chat] auto document generation failed: {gen_exc}")
            traceback.print_exc()
            return None


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
        # Title заполняем по первому сообщению (см. send_message_stream),
        # чтобы в UI не показывать всегда "Новый чат".
        title=None,
        user_id=current_user.id,
    )
    db.add(new_chat)
    await db.commit()
    await db.refresh(new_chat)
    return ChatResponse.model_validate(new_chat)


def _extract_chat_title(text: str) -> str:
    """
    Короткое название темы чата (как в типичных нейросетевых чатах):
    одно-два слова по смыслу, без обрывка личной истории из первого сообщения.
    """
    raw = (text or "").strip()
    if not raw:
        return "Правовой вопрос"

    s = " ".join(raw.split())
    s = re.sub(r"\b(пожалуйста|спасибо)\b.*$", "", s, flags=re.IGNORECASE).strip()
    if not s:
        return "Правовой вопрос"

    s_lower = s.lower()

    # Правила по убыванию специфичности: первое совпадение задаёт короткое имя темы.
    _TITLE_RULES: List[Tuple[re.Pattern, str]] = [
        (
            re.compile(
                r"уволил|уволили|увольнен|увольнение|сокращени|сократили|"
                r"по\s+сокращению|сокращение\s+штата|уменьшени[ея]\s+штата|"
                r"не\s*законн\w*\s*увольн|незаконн\w*\s*увольн",
                re.IGNORECASE,
            ),
            "Увольнение",
        ),
        (
            re.compile(
                r"отпуск|больничн|заработн|зарплат|трудов(ой|ые)|кадров|тк\s*рф|трудовой\s+договор",
                re.IGNORECASE,
            ),
            "Трудовой вопрос",
        ),
        (
            re.compile(r"исков|исковое|подать\s+иск|иск\s+о\s", re.IGNORECASE),
            "Иск",
        ),
        (re.compile(r"претенз", re.IGNORECASE), "Претензия"),
        (
            re.compile(
                r"жалоб(а|у)|апелляц|кассац|частн\w*\s+жалоб",
                re.IGNORECASE,
            ),
            "Жалоба",
        ),
        (re.compile(r"расторг", re.IGNORECASE), "Расторжение договора"),
        (re.compile(r"банкрот|несостоятельност", re.IGNORECASE), "Банкротство"),
        (re.compile(r"алимент", re.IGNORECASE), "Алименты"),
        (re.compile(r"неустойк", re.IGNORECASE), "Неустойка"),
        (
            re.compile(
                r"взыскан|взыскать|задолжен|долг(\s|$)|кредит|займ|ипотек",
                re.IGNORECASE,
            ),
            "Задолженность",
        ),
        (re.compile(r"наследств", re.IGNORECASE), "Наследство"),
        (
            re.compile(r"жкх|коммунал|коммунальн", re.IGNORECASE),
            "ЖКХ",
        ),
        (
            re.compile(
                r"потребител|возврат|гарантий|магазин|услуг[аи]",
                re.IGNORECASE,
            ),
            "Защита прав потребителей",
        ),
        (re.compile(r"аренд", re.IGNORECASE), "Аренда"),
        (re.compile(r"дтп|осаго|страхов", re.IGNORECASE), "ДТП и страхование"),
    ]

    for pattern, title in _TITLE_RULES:
        if pattern.search(s_lower):
            return capitalize_first_letter(title[:200])

    # Нет явной категории — убираем «мне N лет», «меня», «я» и берём очень короткий хвост или общий ярлык.
    t = re.sub(r"\bмне\s+\d{1,3}\s*(лет|года|год)\b", " ", s, flags=re.IGNORECASE)
    t = re.sub(
        r"^(\s*(мне|меня|у\s+меня|я|мой|моя|моё|нас|нам)\s+)+",
        "",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(r"\s+", " ", t).strip().rstrip(".!?")

    # Убираем типовые вопросительные вступления
    t = re.sub(
        r"^(как|что|можно|нужно|подскажите|помогите|требуется|необходимо|скажите|разъясните)\s+",
        "",
        t,
        flags=re.IGNORECASE,
    ).strip()

    words = re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", t)
    if not words:
        return "Правовой вопрос"

    short = " ".join(words[:4]).strip()
    if len(short) > 40:
        short = short[:40].rsplit(" ", 1)[0].strip()

    # Если после очистки всё ещё похоже на бытовую тираду — не показываем как тему
    if len(words) > 8 or len(short) > 35:
        return "Правовой вопрос"

    return capitalize_first_letter(short[:200]) if short else "Правовой вопрос"

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

        # 2.5. Название чата — только эвристика (без второго запроса к GigaChat).
        # Параллельный LLM для title давал двойную нагрузку на API и мог «вешать» ответ.
        default_titles = {"", "Новый чат", "new chat", "New chat"}
        normalized_existing_title = (chat_obj.title or "").strip()
        new_title: Optional[str] = None
        if normalized_existing_title in default_titles:
            extracted = _extract_chat_title(message_in.content)
            if extracted and extracted.strip():
                new_title = extracted.strip()[:200]
                chat_obj.title = new_title
                db.add(chat_obj)
                await db.commit()
                await db.refresh(chat_obj)

        # 3. Создаем пустое сообщение ассистента
        assistant_message = Message(
            chat_id=chat_id,
            content="",
            role="assistant"
        )
        db.add(assistant_message)
        await db.commit()
        await db.refresh(assistant_message)

        # 4. Контекст для промпта: изменения в законах + загруженные шаблоны (для [AUTO_DOC]).
        law_lines: list[str] = []
        law_db_size = 0
        try:
            recent_laws = await _law_change_crud.get_multi(db, limit=3)
            law_lines = [f"Изменение: {law.change_title}" for law in recent_laws]
            law_db_size = await _law_change_crud.count(db)
        except Exception as context_error:
            print(f"⚠️ RAG context unavailable: {context_error}")

        tpl_result = await db.execute(
            select(StoredDocument)
            .where(
                StoredDocument.user_id == current_user.id,
                StoredDocument.status == "ready",
                StoredDocument.file_path.isnot(None),
                StoredDocument.type.in_(["upload", "template"]),
            )
            .order_by(StoredDocument.created_at.desc())
            .limit(30)
        )
        user_template_rows = [(d.id, d.title) for d in tpl_result.scalars().all()]
        template_rows = list_builtin_templates() + user_template_rows
        context_str = _build_chat_context_text(law_lines, law_db_size, template_rows)
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
        stream_text = ""
        persisted = False
        try:
            if new_title:
                yield f"data: {json.dumps({'title': new_title}, ensure_ascii=False)}\n\n"

            # История диалога нужна модели, чтобы НЕ повторять вопросы и использовать уже данные факты.
            # Берём последние сообщения (включая только что сохранённое сообщение пользователя).
            history_limit = 20
            history_result = await db.execute(
                select(Message)
                .where(Message.chat_id == chat_id)
                .order_by(Message.created_at.desc())
                .limit(history_limit)
            )
            history_messages = list(reversed(history_result.scalars().all()))
            chat_history = "\n".join(
                f"{m.role}: {m.content}".strip()
                for m in history_messages
                if (m.content or "").strip()
            )

            try:
                full_response = await asyncio.wait_for(
                    _nlp_service.generate_response(
                        user_query=message_in.content,
                        context=context_str,
                        chat_history=chat_history,
                    ),
                    timeout=float(settings.GIGACHAT_GENERATE_TIMEOUT_SECONDS),
                )
            except asyncio.TimeoutError:
                full_response = (
                    f"Превышено время ожидания ответа GigaChat ({settings.GIGACHAT_GENERATE_TIMEOUT_SECONDS} с). "
                    "Проверьте сеть, ключи в .env и повторите запрос."
                )

            visible, auto_spec = _extract_auto_doc_block(full_response)
            if visible.strip():
                stream_text = visible
            elif auto_spec:
                stream_text = (
                    "Ответ сформирован; документ по рекомендации создан и доступен в разделе «Документы»."
                )
            else:
                stream_text = full_response or ""

            # Стриминг по символам-блокам с сохранением пробелов и переносов
            chunk_size = 24
            for i in range(0, len(stream_text), chunk_size):
                part = stream_text[i : i + chunk_size]
                chunk = f"data: {json.dumps({'content': part}, ensure_ascii=False)}\n\n"
                yield chunk
                await asyncio.sleep(0.05)

            gen_payload: Optional[dict[str, str]] = None
            if auto_spec:
                doc_ready = await _try_auto_generate_document(
                    current_user,
                    spec=auto_spec,
                    template_rows=template_rows,
                    user_query=message_in.content,
                    chat_history=chat_history,
                )
                if doc_ready and doc_ready.status == "ready":
                    gen_payload = {"id": doc_ready.id, "title": doc_ready.title}

<<<<<<< HEAD
            if gen_payload:
                yield f"data: {json.dumps({'generated_document': gen_payload}, ensure_ascii=False)}\n\n"

            await _persist_assistant_message(assistant_message.id, stream_text)
            persisted = True

            yield f"data: {json.dumps({'message_id': assistant_message.id}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        except Exception as e:
            error_text = f"Ошибка GigaChat: {str(e)}"
            stream_text = error_text
            try:
                await _persist_assistant_message(assistant_message.id, error_text)
                persisted = True
            except Exception:
                traceback.print_exc()
=======
            # Обновляем финальный ответ ассистента
            await db.execute(
                update(Message)
                .where(Message.id == assistant_message.id)
                .values(content=full_response)
            )
            await db.commit()

        except Exception as e:
            error_text = f"Ошибка GigaChat: {str(e)}"
            await db.execute(
                update(Message)
                .where(Message.id == assistant_message.id)
                .values(content=error_text)
            )
            await db.commit()
>>>>>>> be87a3ca7d57fae1fb1eaece8a41ae6fc5b182a6
            yield f"data: {json.dumps({'content': error_text}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'message_id': assistant_message.id}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        finally:
            if not persisted:
                try:
                    await _persist_assistant_message(assistant_message.id, stream_text)
                except Exception:
                    traceback.print_exc()
    
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

