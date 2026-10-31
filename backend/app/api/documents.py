import logging
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.chat import ChatSession, Message
from app.models.court_filing import CourtFiling
from app.models.document import Document
from app.models.user import User
from app.schemas.document import (
    DocumentOut,
    DocumentPlaceholdersResponse,
    DocumentTemplateOut,
    FillUploadedTemplateRequest,
    GenerateAiDocumentRequest,
    GenerateDocumentRequest,
    SuggestDocumentFieldsRequest,
    SuggestDocumentFieldsResponse,
    UploadDocumentResponse,
)
from app.services.document_ai_generator import generate_ai_document_text
from app.services.document_field_context import merge_user_over_suggested, suggest_fields_for_template
from app.services.document_templates import (
    TEMPLATES,
    RenderedTemplate,
    build_docx_bytes,
    build_pdf_bytes,
    list_templates_meta,
    render_template,
)
from app.services.docx_fill import collect_placeholder_keys_from_docx, fill_docx_template
from app.schemas.document_workflow import StartDocumentInterview

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["Documents"])


@router.get("/scenarios")
async def list_document_scenarios(current_user: User = Depends(get_current_user)):
    from app.services.document_scenarios import SCENARIOS
    from app.services.document_catalog import catalog_forms
    return [{**SCENARIOS[row['scenario']].as_dict(), 'coverage':'structured', 'docx_template':True,
             'lawyer_reviewed':False,'content_status':row['content_status']} for row in catalog_forms()]


@router.get('/catalog')
async def list_supported_forms(current_user: User = Depends(get_current_user)):
    from app.services.document_catalog import catalog_forms
    return {'revision':'2026-10-29','forms':catalog_forms(), 'scope':'curated_forms_only'}


@router.get('/form-sources')
async def list_form_sources(q: str = Query(default='', max_length=500),
        document_kind: str | None = Query(default=None, pattern='^(contract|claim|complaint|pretense|act|receipt|procedural|appeal|authority)$'),
        limit: int = Query(default=20, ge=1, le=100), current_user: User = Depends(get_current_user)):
    from app.services.document_source_rag import search_form_sources
    return search_form_sources(q, document_kind=document_kind, limit=limit)


@router.post("/interviews", status_code=201)
async def start_document_interview(
    payload: StartDocumentInterview,
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    from app.services.document_workflow import new_state
    from app.services.document_conversation import conversational_interview_turn
    from app.services.llm_cost import record_llm_usage
    context = ""
    if payload.chat_id is not None:
        try:
            await _chat_context_text(db, user_id=current_user.id, chat_id=payload.chat_id)
        except HTTPException as exc:
            if exc.status_code != 404:raise
            raise HTTPException(404, detail={
                'code':'chat_context_unavailable',
                'message':'Выбранный чат недоступен. Подготовку можно начать заново по вашему описанию.',
            }) from exc
        # Assistant suggestions/examples are not facts supplied by the user.
        previous = (await db.execute(select(Message).where(Message.chat_id == payload.chat_id,
                    Message.role == "user").order_by(Message.id.asc()))).scalars().all()
        context = "\n".join(m.content for m in previous)
    state = new_state(payload.prompt, context=context[-30000:], title=payload.title,
                      document_type=payload.document_type, filename=payload.filename, output_format=payload.output_format)
    try:
        state, answer, usage = await conversational_interview_turn(state, payload.prompt)
    except (RuntimeError, ValueError) as exc:
        logger.warning("Document interview failed: %s", type(exc).__name__)
        raise HTTPException(502, "Не удалось начать уточнение документа. Повторите запрос.") from exc
    from app.services.chat_titles import suggest_chat_title
    title=payload.title or suggest_chat_title(state,payload.prompt)
    state['title_manual']=bool(payload.title)
    state['automatic_title']=title
    chat = ChatSession(user_id=current_user.id, title=title, document_workflow=state)
    db.add(chat)
    await db.flush()
    answer = await interview_file_reply(chat, current_user.id, db, answer)
    db.add(Message(chat_id=chat.id, role="user", content=payload.prompt))
    await db.flush()
    reply = Message(chat_id=chat.id, role="assistant", content=answer)
    db.add(reply)
    await db.flush()
    await record_llm_usage(db, user_id=current_user.id, chat_id=chat.id, message_id=reply.id,
                           model=settings.GIGACHAT_MODEL, cached=False, usage=usage, commit=False)
    await db.commit()
    return {"chat_id": chat.id}


async def _owned_interview(db, chat_id, user_id):
    chat = (await db.execute(select(ChatSession).where(ChatSession.id == chat_id, ChatSession.user_id == user_id))).scalar_one_or_none()
    if chat is None or not chat.document_workflow:
        raise HTTPException(404, "Подготовка документа не найдена")
    return chat


@router.get("/interviews/{chat_id}")
async def get_document_interview(chat_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    chat = await _owned_interview(db, chat_id, current_user.id)
    from app.services.document_scenarios import SCENARIOS
    from app.services.document_workflow import sanitize_interview
    state = sanitize_interview(chat.document_workflow)
    scenario = SCENARIOS.get(state.get("scenario"))
    return {**state, "document_title": scenario.title if scenario else ""}


@router.post("/interviews/{chat_id}/export", response_model=UploadDocumentResponse, status_code=201)
async def export_document_interview(chat_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    chat = await _owned_interview(db, chat_id, current_user.id)
    result = await prepare_interview_file(chat, current_user.id, db)
    await db.commit()
    return result


async def prepare_interview_file(chat, user_id, db):
    """Create the actual artifact before a chat reply promises a download."""
    from app.services.document_scenarios import SCENARIOS, render_scenario
    from app.services.document_workflow import pending_fields, sanitize_interview
    from app.services.document_drafting import prepare_document_draft, presentation_fields, narrative_keys, facts_digest, DraftPreparationError, draft_is_current
    from app.services.document_export_contract import EDITOR_VERSION, export_package, validate_export_blocks
    chat_id = chat.id
    state = sanitize_interview(chat.document_workflow)
    if state.get('scenario'):
        state['text_package'] = export_package(state.get('text_package'), SCENARIOS[state['scenario']])
    if state.get("phase") != "ready" or not state.get("scenario") or pending_fields(state):
        raise HTTPException(409, "Сначала завершите заполнение или отметьте неизвестные поля в чате")
    from app.services.document_quality import quality_issues
    issues = quality_issues(state)
    if issues:
        raise HTTPException(409, issues[0]["question"])
    import hashlib
    import json
    file_digest = hashlib.sha256(json.dumps({
        'export_contract': EDITOR_VERSION,
        'case_facts':state.get('case_facts'),
        "facts": facts_digest(state["fields"]), "package": state.get("text_package"),
        "format": state.get("output_format", "docx"), "filename": state.get("filename"),
    }, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    saved = state.get("generated_document", {})
    if saved.get("digest") == file_digest and not state.get('form_review_fields'):
        document = (await db.execute(select(Document).where(
            Document.id == saved.get("document_id"), Document.user_id == user_id
        ))).scalar_one_or_none()
        if document and document.file_path and Path(document.file_path).is_file():
            return UploadDocumentResponse(document_id=document.id, filename=document.title, status=document.status)
    scenario = SCENARIOS[state["scenario"]]
    from app.services.document_schema import readiness_report
    state['readiness'] = readiness_report(state, state.get('text_package'))
    if narrative_keys(state) and not draft_is_current(state):
        from app.services.gigachat_client import get_gigachat_client
        from app.services.llm_cost import record_llm_usage
        try:
            editor = await get_gigachat_client()
            try:
                state, usage = await prepare_document_draft(state, editor)
            except DraftPreparationError as exc:
                # Preserve verified paragraphs and retry only the rejected ones.
                state = exc.partial_state
                state, usage = await prepare_document_draft(state, editor)
        except (RuntimeError, ValueError) as exc:
            from app.services.document_form_rules import uses_form_composer
            if uses_form_composer(state):
                from app.services.document_form_composition import prepare_form_document
                state,usage=await prepare_form_document(state,None)
            else:
                if hasattr(exc, "partial_state"):
                    state = exc.partial_state
                if isinstance(exc, DraftPreparationError):
                    state = exc.partial_state
                    state["draft_failure_fields"] = exc.keys
                state["draft_error"] = "editor_unavailable" if not isinstance(exc, DraftPreparationError) else "editor_validation"
                chat.document_workflow = state
                raise HTTPException(502, "Факты сохранены, но официальную редакцию пока не удалось проверить. Повторите подготовку файла.") from exc
        await record_llm_usage(db, user_id=user_id, chat_id=chat.id, message_id=None,
                               model=settings.GIGACHAT_MODEL, cached=False, usage=usage, commit=False)
    chat.document_workflow = state
    state['readiness']=readiness_report(state,state.get('text_package'))
    document_fields = presentation_fields(state)
    for key in state.get('form_review_fields',[]):
        state['readiness']['legal_review'].append({'field':key,'label':next((f.label for f in scenario.fields if f.key==key),key)})
        state['readiness']['status']='incomplete_draft'
    from app.services.document_case_composition import uses_case_composer, prepare_case_document
    if uses_case_composer(state):
        state=prepare_case_document(state)
        document_fields=presentation_fields(state)
        for key in state.get('composition_review_fields',[]):
            state['readiness']['legal_review'].append({'field':key,'label':next((f.label for f in scenario.fields if f.key==key),key)})
            state['readiness']['status']='incomplete_draft'
        chat.document_workflow=state
    package = state.get("text_package")
    if package:
        from app.services.document_template_library import render_package_blocks, format_template_fields
        final_blocks = render_package_blocks(package, scenario, document_fields, format_template_fields(scenario, document_fields))
        validate_export_blocks(final_blocks)
    rendered = RenderedTemplate(key=scenario.key, title=scenario.title,
        description="Черновик по шаблону из открытых источников" if package else "Черновая структура: юридический текст ещё не проверен",
        rendered_text=render_scenario(scenario, document_fields, package))
    output_format = state.get("output_format", "docx")
    if not (package and output_format in {'docx','pdf'}):
        content = (build_pdf_bytes(rendered) if output_format == "pdf" else
                   rendered.rendered_text.encode("utf-8") if output_format == "txt" else build_docx_bytes(rendered))
    if package and output_format in {"docx", "pdf"}:
        from app.services.document_template_library import render_package_blocks, format_template_fields
        from app.services.document_workflow_docx import build_legal_docx, build_legal_pdf
        blocks = render_package_blocks(package, scenario, document_fields, format_template_fields(scenario, document_fields))
        note = "Проект по открытым источникам. Требуется проверка юристом." if package.get("review_status") != "lawyer_reviewed" else "Черновик. Проверьте заполненные сведения перед использованием."
        if package.get('docx_asset'):
            from app.services.document_docx_template import fill_docx_template, docx_to_pdf, docx_review_fields
            labels={spec.key:spec.label for spec in scenario.fields}
            for key in docx_review_fields(document_fields):
                if not any(item['field']==key for item in state['readiness']['legal_review']):
                    state['readiness']['legal_review'].append({'field':key,'label':labels[key]})
                state['readiness']['status']='incomplete_draft'
            content = fill_docx_template(package, scenario, document_fields)
            if output_format == 'pdf':
                import asyncio
                content = await asyncio.to_thread(docx_to_pdf, content)
        else:
            content = build_legal_docx(scenario.title, blocks, review_note=note) if output_format == "docx" else build_legal_pdf(scenario.title, blocks, review_note=note)
    filename = Path(_sanitize_filename(state.get("filename", "document-draft"))).stem + "." + output_format
    doc_id = str(uuid4())
    target = _storage_root() / f"{doc_id}_{filename}"
    target.write_bytes(content)
    document = Document(id=doc_id, user_id=user_id, title=filename, type="generated", status="ready",
        file_path=str(target), file_size=len(content),
        mime_type=("application/pdf" if output_format == "pdf" else "text/plain; charset=utf-8" if output_format == "txt"
                   else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        generation_meta={"source": "structured_interview", "chat_id": chat_id, "scenario": scenario.key,
                         "template_version": package["version"] if package else scenario.version,
                         "review_status": package.get("review_status", "source_checked_draft") if package else scenario.review_status,
                         "template_source": package,
                         "docx_asset": package.get('docx_asset') if package else None,
                         "revision": state["revision"], "fields": state["fields"],
                         "readiness": state['readiness'],
                         "draft_fields": state.get("draft_fields", {}), "draft_digest": state.get("draft_digest")})
    db.add(document)
    state["generated_document"] = {"document_id": doc_id, "filename": filename, "digest": file_digest}
    chat.document_workflow = state
    await db.flush()
    return UploadDocumentResponse(document_id=document.id, filename=filename, status=document.status)


async def interview_file_reply(chat, user_id, db, fallback):
    if chat.document_workflow.get("phase") != "ready":
        return fallback
    from app.services.document_quality import quality_issues
    issues = quality_issues(chat.document_workflow)
    if issues:
        from copy import deepcopy
        state = deepcopy(chat.document_workflow)
        issue = issues[0]
        state.update(phase="collecting", last_questions=[issue["field"]], quality_issues=issues)
        state["fields"][issue["field"]].update(status="incomplete", error=issue["question"])
        chat.document_workflow = state
        return "Перед подготовкой файла нужно устранить противоречие. " + issue["question"]
    try:
        document = await prepare_interview_file(chat, user_id, db)
    except (HTTPException, RuntimeError, ValueError, OSError) as exc:
        from app.services.document_drafting import DraftPreparationError
        cause = exc.__cause__
        if isinstance(cause, DraftPreparationError):
            from copy import deepcopy
            state = deepcopy(chat.document_workflow)
            # A failed editor is not missing user evidence. Keep the cursor and
            # original confirmed facts; the cached successful edits survive.
            state['draft_failure_fields'] = cause.keys
            chat.document_workflow = state
            logger.warning("Interview editorial validation: chat=%s fields=%s", chat.id, cause.keys)
            return 'Все ваши ответы сохранены. Редактор не прошёл проверку формулировок, поэтому файл пока не выдан. Повторять сведения не нужно. Напишите «пришли файл», чтобы повторить подготовку.'
        logger.warning("Interview artifact unavailable: chat=%s kind=%s", chat.id, type(exc).__name__)
        return "Данные сохранены. Подготовить файл сейчас не удалось. Напишите «пришли файл», чтобы повторить создание документа."
    # Only a persisted, owned file gets a download link. Model prose cannot
    # replace this server-controlled completion message.
    name = document.filename.replace("[", "").replace("]", "")
    report = chat.document_workflow.get('readiness', {})
    notice = 'Черновик подготовлен. Перед использованием проверьте факты и незаполненные поля.'
    missing = [item['label'] for item in report.get('missing', []) + report.get('legal_review', [])]
    if missing:
        notice += ' Нужно дополнить или проверить: ' + '; '.join(missing[:5]) + ('; остальные пропуски отмечены в документе.' if len(missing) > 5 else '.')
    if report.get('actions'): notice += ' ' + ' '.join(report['actions'])
    if report.get('coverage') == 'basic': notice += ' Для этого вида документа используется базовая структура; полноту разделов нужно проверить отдельно.'
    return (notice +
            f"\n\n[Скачать {name}](/documents/{document.document_id}/download)")

ALLOWED_UPLOAD_SUFFIXES = {
    ".pdf",
    ".docx",
    ".txt",
    ".doc",
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
}


def _is_docx_document(document: Document) -> bool:
    if document.file_path and Path(document.file_path).suffix.lower() == ".docx":
        return True
    title = (document.title or "").lower()
    if title.endswith(".docx"):
        return True
    mt = (document.mime_type or "").lower()
    return "wordprocessingml" in mt


def _storage_root() -> Path:
    root = Path(settings.DOCUMENTS_STORAGE_DIR).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _sanitize_filename(filename: str) -> str:
    cleaned = Path(filename).name.strip()
    return cleaned or "document.txt"


async def _chat_context_text(db: AsyncSession, *, user_id: int, chat_id: int) -> str:
    chat_r = await db.execute(
        select(ChatSession).where(ChatSession.id == chat_id, ChatSession.user_id == user_id)
    )
    if chat_r.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    msg_r = await db.execute(
        select(Message).where(Message.chat_id == chat_id).order_by(Message.created_at.asc(), Message.id.asc())
    )
    lines: list[str] = []
    for msg in msg_r.scalars():
        lines.append(f"{msg.role}: {msg.content}")
    return "\n".join(lines)


async def _filing_fields_map(db: AsyncSession, *, user_id: int, court_filing_id: int) -> dict[str, str]:
    res = await db.execute(
        select(CourtFiling).where(CourtFiling.id == court_filing_id, CourtFiling.user_id == user_id)
    )
    filing = res.scalar_one_or_none()
    if filing is None:
        raise HTTPException(status_code=404, detail="Court filing not found")
    return {"case_number": filing.case_number, "court_name": filing.court_name}


@router.post("/upload", response_model=UploadDocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    filename = _sanitize_filename(file.filename or "document.bin")
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_SUFFIXES:
        raise HTTPException(status_code=422, detail="Unsupported file extension")

    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=422, detail="Uploaded file is empty")

    document_id = str(uuid4())
    storage_path = _storage_root() / f"{document_id}_{filename}"
    storage_path.write_bytes(payload)

    document = Document(
        id=document_id,
        user_id=current_user.id,
        title=filename,
        type="upload",
        status="ready",
        file_path=str(storage_path),
        file_size=len(payload),
        mime_type=file.content_type or "application/octet-stream",
    )
    db.add(document)
    await db.commit()

    logger.info("Document uploaded: document_id=%s user_id=%s", document.id, current_user.id)
    return UploadDocumentResponse(document_id=document.id, filename=document.title, status=document.status)


@router.post("/generate", response_model=UploadDocumentResponse, status_code=status.HTTP_201_CREATED)
async def generate_document(
    payload: GenerateDocumentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    filename = _sanitize_filename(payload.filename)

    template = TEMPLATES.get(payload.template_key)
    if template is None:
        raise HTTPException(status_code=422, detail=f"Unknown template_key: {payload.template_key}")

    context_text = ""
    filing_fields: dict[str, str] | None = None
    if payload.chat_id is not None:
        context_text = await _chat_context_text(db, user_id=current_user.id, chat_id=payload.chat_id)
    if payload.court_filing_id is not None:
        filing_fields = await _filing_fields_map(
            db, user_id=current_user.id, court_filing_id=payload.court_filing_id
        )

    suggested, field_sources = suggest_fields_for_template(
        payload.template_key,
        context_text=context_text,
        filing_fields=filing_fields,
    )
    merged_fields = merge_user_over_suggested(suggested, payload.fields)

    generation_meta = {
        "template_key": payload.template_key,
        "template_version": template.version,
        "chat_id": payload.chat_id,
        "court_filing_id": payload.court_filing_id,
        "field_sources": field_sources,
    }

    try:
        rendered = render_template(
            payload.template_key,
            merged_fields,
            template_version=payload.template_version,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if payload.output_format == "docx":
        if not filename.lower().endswith(".docx"):
            filename = f"{filename}.docx"
        body = build_docx_bytes(rendered)
        mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif payload.output_format == "pdf":
        if not filename.lower().endswith(".pdf"):
            filename = f"{filename}.pdf"
        body = build_pdf_bytes(rendered)
        mime_type = "application/pdf"
    else:
        if not filename.lower().endswith(".txt"):
            filename = f"{filename}.txt"
        body = rendered.rendered_text.encode("utf-8")
        mime_type = "text/plain"

    document_id = str(uuid4())
    storage_path = _storage_root() / f"{document_id}_{filename}"
    storage_path.write_bytes(body)

    document = Document(
        id=document_id,
        user_id=current_user.id,
        title=filename,
        type="generated",
        status="ready",
        file_path=str(storage_path),
        file_size=len(body),
        mime_type=mime_type,
        generation_meta=generation_meta,
    )
    db.add(document)
    await db.commit()

    logger.info(
        "Document generated from template: document_id=%s user_id=%s template=%s",
        document.id,
        current_user.id,
        payload.template_key,
    )
    return UploadDocumentResponse(document_id=document.id, filename=document.title, status=document.status)


@router.post("/generate-ai", response_model=UploadDocumentResponse, status_code=status.HTTP_201_CREATED)
async def generate_ai_document(
    payload: GenerateAiDocumentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Сгенерировать документ по текстовому запросу пользователя (GigaChat)."""
    context_text = ""
    if payload.chat_id is not None:
        context_text = await _chat_context_text(db, user_id=current_user.id, chat_id=payload.chat_id)

    try:
        doc_title, doc_body = await generate_ai_document_text(
            payload.prompt,
            context_text=context_text,
            document_type_hint=payload.document_type,
            title_hint=payload.title,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("generate_ai_document failed")
        raise HTTPException(status_code=502, detail="Не удалось сгенерировать документ. Попробуйте позже.") from exc

    rendered = RenderedTemplate(
        key="ai_generated",
        title=doc_title,
        description="Сгенерировано ИИ по запросу пользователя",
        rendered_text=doc_body,
    )

    filename = _sanitize_filename(payload.filename)
    if payload.output_format == "docx":
        if not filename.lower().endswith(".docx"):
            filename = f"{filename}.docx"
        body = build_docx_bytes(rendered)
        mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif payload.output_format == "pdf":
        if not filename.lower().endswith(".pdf"):
            filename = f"{filename}.pdf"
        body = build_pdf_bytes(rendered)
        mime_type = "application/pdf"
    else:
        if not filename.lower().endswith(".txt"):
            filename = f"{filename}.txt"
        body = doc_body.encode("utf-8")
        mime_type = "text/plain"

    document_id = str(uuid4())
    storage_path = _storage_root() / f"{document_id}_{filename}"
    storage_path.write_bytes(body)

    generation_meta = {
        "source": "ai_generated",
        "document_title": doc_title,
        "document_type": payload.document_type,
        "chat_id": payload.chat_id,
        "prompt_preview": payload.prompt[:500],
    }

    document = Document(
        id=document_id,
        user_id=current_user.id,
        title=filename,
        type="generated",
        status="ready",
        file_path=str(storage_path),
        file_size=len(body),
        mime_type=mime_type,
        generation_meta=generation_meta,
    )
    db.add(document)
    await db.commit()

    logger.info(
        "AI document generated: document_id=%s user_id=%s title=%s",
        document.id,
        current_user.id,
        doc_title,
    )
    return UploadDocumentResponse(document_id=document.id, filename=document.title, status=document.status)


@router.post("/fill-uploaded-template", response_model=UploadDocumentResponse, status_code=status.HTTP_201_CREATED)
async def fill_uploaded_docx_template(
    payload: FillUploadedTemplateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Заполняет загруженный .docx: в файле используйте плейсхолдеры {{field_name}} (латиница, цифры, _)."""
    res = await db.execute(
        select(Document).where(
            Document.id == payload.template_document_id,
            Document.user_id == current_user.id,
        )
    )
    template_doc = res.scalar_one_or_none()
    if template_doc is None:
        raise HTTPException(status_code=404, detail="Template document not found")
    if not template_doc.file_path:
        raise HTTPException(status_code=422, detail="Template document has no file")
    if not _is_docx_document(template_doc):
        raise HTTPException(status_code=422, detail="Template must be a .docx file")

    src_path = Path(template_doc.file_path)
    if not src_path.exists():
        raise HTTPException(status_code=404, detail="Template file is missing on disk")

    filename = _sanitize_filename(payload.filename)
    if not filename.lower().endswith(".docx"):
        filename = f"{filename}.docx"

    try:
        body = fill_docx_template(src_path, payload.fields)
    except Exception as exc:
        logger.exception("fill_uploaded_docx_template failed")
        raise HTTPException(status_code=422, detail=f"Failed to process DOCX: {exc}") from exc

    document_id = str(uuid4())
    storage_path = _storage_root() / f"{document_id}_{filename}"
    storage_path.write_bytes(body)

    generation_meta = {
        "source": "uploaded_docx_template",
        "template_document_id": payload.template_document_id,
        "placeholders_filled": list(payload.fields.keys()),
    }

    document = Document(
        id=document_id,
        user_id=current_user.id,
        title=filename,
        type="generated",
        status="ready",
        file_path=str(storage_path),
        file_size=len(body),
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        generation_meta=generation_meta,
    )
    db.add(document)
    await db.commit()

    logger.info(
        "Document filled from uploaded template: document_id=%s user_id=%s template_id=%s",
        document.id,
        current_user.id,
        payload.template_document_id,
    )
    return UploadDocumentResponse(document_id=document.id, filename=document.title, status=document.status)


@router.post("/suggest-fields", response_model=SuggestDocumentFieldsResponse)
async def suggest_document_fields(
    payload: SuggestDocumentFieldsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    template = TEMPLATES.get(payload.template_key)
    if template is None:
        raise HTTPException(status_code=422, detail=f"Unknown template_key: {payload.template_key}")

    context_text = ""
    filing_fields: dict[str, str] | None = None
    if payload.chat_id is not None:
        context_text = await _chat_context_text(db, user_id=current_user.id, chat_id=payload.chat_id)
    if payload.court_filing_id is not None:
        filing_fields = await _filing_fields_map(
            db, user_id=current_user.id, court_filing_id=payload.court_filing_id
        )

    suggested, sources = suggest_fields_for_template(
        payload.template_key,
        context_text=context_text,
        filing_fields=filing_fields,
    )
    return SuggestDocumentFieldsResponse(
        suggested=suggested,
        sources=sources,
        template_version=template.version,
    )


@router.get("/templates", response_model=list[DocumentTemplateOut])
async def list_document_templates(
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    return list_templates_meta()


@router.get("", response_model=list[DocumentOut])
async def list_documents(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document).where(Document.user_id == current_user.id).order_by(Document.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{document_id}/placeholders", response_model=DocumentPlaceholdersResponse)
async def get_docx_template_placeholders(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.user_id == current_user.id)
    )
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if not document.file_path:
        raise HTTPException(status_code=422, detail="Document has no file")
    if not _is_docx_document(document):
        raise HTTPException(status_code=422, detail="Only .docx templates support placeholder scan")

    path = Path(document.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Document file is missing on disk")

    try:
        keys = collect_placeholder_keys_from_docx(path)
    except Exception as exc:
        logger.exception("get_docx_template_placeholders failed")
        raise HTTPException(status_code=422, detail=f"Failed to read DOCX: {exc}") from exc

    return DocumentPlaceholdersResponse(keys=keys)


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.user_id == current_user.id)
    )
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.get("/{document_id}/download")
async def download_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.user_id == current_user.id)
    )
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if not document.file_path:
        raise HTTPException(status_code=404, detail="Document file is missing")

    file_path = Path(document.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Document file is missing")
    return FileResponse(path=file_path, filename=document.title, media_type=document.mime_type)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.user_id == current_user.id)
    )
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    if document.file_path:
        file_path = Path(document.file_path)
        if file_path.exists():
            file_path.unlink()

    await db.delete(document)
    await db.commit()
