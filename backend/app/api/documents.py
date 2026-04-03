import mimetypes
import os
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import delete as sql_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.document import Document
from app.schemas.document import (
    DocumentGenerateRequest,
    DocumentOut,
    UploadDocumentResponse,
)
from app.services.document_generation import DocumentGenerationService
from app.services.builtin_templates import BUILTIN_PREFIX, resolve_builtin_template_path
from app.core.config import settings
from app.utils.text import capitalize_filename, capitalize_first_letter


router = APIRouter(prefix="/documents", tags=["Documents"])
_doc_gen = DocumentGenerationService()


def _get_storage_root() -> Path:
    root = Path(settings.DOCUMENTS_STORAGE_PATH)
    if not root.is_absolute():
        root = Path.cwd() / root
    return root


def _guess_mime_type(filename: str, content_type: str | None) -> str:
    if content_type:
        return content_type
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


@router.post("/upload", response_model=UploadDocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    allowed_ext = {".pdf", ".docx", ".doc", ".rtf", ".txt"}
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in allowed_ext:
        raise HTTPException(status_code=400, detail=f"Unsupported extension: {suffix}")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    storage_root = _get_storage_root()
    user_dir = storage_root / str(current_user.id)
    user_dir.mkdir(parents=True, exist_ok=True)

    doc_id = str(uuid4())
    safe_original = os.path.basename(file.filename or f"document{suffix}")
    safe_original = capitalize_filename(safe_original)
    stored_filename = f"{doc_id}_{safe_original}"
    stored_path = user_dir / stored_filename

    stored_path.write_bytes(content)

    mime_type = _guess_mime_type(safe_original, file.content_type)
    file_size = len(content)

    doc = Document(
        id=doc_id,
        user_id=current_user.id,
        title=safe_original,
        type="upload",
        status="ready",
        file_path=str(stored_path),
        file_size=file_size,
        mime_type=mime_type,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    return UploadDocumentResponse(document_id=doc.id, filename=doc.title, status="ready")


async def _list_documents(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    stmt = (
        select(Document)
        .where(Document.user_id == current_user.id)
        .order_by(Document.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return [DocumentOut.model_validate(x) for x in result.scalars().all()]


# Два пути — без редиректа 307, иначе axios/браузер часто теряет Authorization на втором запросе.
router.add_api_route("", _list_documents, methods=["GET"], response_model=list[DocumentOut])
router.add_api_route("/", _list_documents, methods=["GET"], response_model=list[DocumentOut])


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Document).where(Document.id == document_id, Document.user_id == current_user.id)
    result = await db.execute(stmt)
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentOut.model_validate(doc)


@router.get("/{document_id}/download")
async def download_document(
    document_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Document).where(Document.id == document_id, Document.user_id == current_user.id)
    result = await db.execute(stmt)
    doc = result.scalar_one_or_none()
    if not doc or not doc.file_path:
        raise HTTPException(status_code=404, detail="File not found")

    file_path = Path(doc.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    media_type = doc.mime_type or mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"

    return FileResponse(
        str(file_path),
        media_type=media_type,
        filename=doc.title,
    )


@router.delete("/all")
async def delete_all_documents(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Удалить все документы текущего пользователя (файлы на диске и записи в БД)."""
    result = await db.execute(select(Document).where(Document.user_id == current_user.id))
    docs = list(result.scalars().all())
    for doc in docs:
        if doc.file_path:
            try:
                Path(doc.file_path).unlink(missing_ok=True)
            except Exception:
                pass
    if docs:
        await db.execute(sql_delete(Document).where(Document.user_id == current_user.id))
        await db.commit()
    return {"deleted": len(docs)}


@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Document).where(Document.id == document_id, Document.user_id == current_user.id)
    result = await db.execute(stmt)
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.file_path:
        try:
            Path(doc.file_path).unlink(missing_ok=True)
        except Exception:
            pass

    await db.delete(doc)
    await db.commit()
    return {"ok": True}


@router.post("/generate", response_model=DocumentOut)
async def generate_document(
    payload: DocumentGenerateRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    template_path: str | None = None
    template_content: str = ""
    template_name = payload.template_id or "template"

    if payload.template_id:
        if payload.template_id.startswith(BUILTIN_PREFIX):
            p, name = resolve_builtin_template_path(payload.template_id)
            if p and name:
                template_path = p
                template_name = name
        else:
            stmt = select(Document).where(
                Document.id == payload.template_id, Document.user_id == current_user.id
            )
            result = await db.execute(stmt)
            template_doc = result.scalar_one_or_none()
            if template_doc and template_doc.file_path:
                template_path = template_doc.file_path
                template_name = template_doc.title

    output_dir = str(_get_storage_root() / str(current_user.id) / "generated")
    doc_id = str(uuid4())

    doc = Document(
        id=doc_id,
        user_id=current_user.id,
        title=capitalize_filename(payload.title or f"{payload.document_type}.{payload.output_format}"),
        type="generated",
        status="processing",
        file_path=None,
        file_size=None,
        mime_type=None,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    try:
        result = await _doc_gen.generate_document_files(
            user_query=payload.user_query,
            document_type=payload.document_type,
            template_name=template_name,
            template_path=template_path,
            output_format=payload.output_format,
            client_data=payload.client_data or {},
            output_dir=output_dir,
            provided_template_content=template_content,
        )

        doc.file_path = result["file_path"]
        doc.file_size = result["file_size"]
        doc.mime_type = result["mime_type"]
        raw_t = payload.title or result["title"]
        doc.title = capitalize_filename(str(raw_t)) if raw_t else capitalize_first_letter(payload.document_type)
        doc.status = "ready"
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
        return DocumentOut.model_validate(doc)
    except Exception:
        doc.status = "error"
        db.add(doc)
        await db.commit()
        raise


__all__ = ["router"]

