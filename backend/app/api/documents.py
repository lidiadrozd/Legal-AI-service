import logging
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
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
    GenerateDocumentRequest,
    SuggestDocumentFieldsRequest,
    SuggestDocumentFieldsResponse,
    UploadDocumentResponse,
)
from app.services.document_field_context import merge_user_over_suggested, suggest_fields_for_template
from app.services.document_templates import (
    TEMPLATES,
    build_docx_bytes,
    build_pdf_bytes,
    list_templates_meta,
    render_template,
)
from app.services.docx_fill import collect_placeholder_keys_from_docx, fill_docx_template

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["Documents"])

ALLOWED_UPLOAD_SUFFIXES = {".pdf", ".docx", ".txt", ".doc"}


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
        select(Message).where(Message.chat_id == chat_id).order_by(Message.created_at.asc())
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
