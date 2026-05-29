"""
Загрузка прикреплённых к сообщению документов и подготовка текста для GigaChat.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.services.document_text_extractor import (
    MAX_DOC_CHARS,
    MAX_TOTAL_CHARS,
    extract_text_from_file,
    truncate_text,
)


async def load_user_documents_text(
    db: AsyncSession,
    *,
    user_id: int,
    document_ids: list[str] | None,
) -> list[dict[str, str]]:
    if not document_ids:
        return []

    result = await db.execute(
        select(Document).where(
            Document.id.in_(document_ids),
            Document.user_id == user_id,
        )
    )
    docs_by_id = {doc.id: doc for doc in result.scalars().all()}

    attached: list[dict[str, str]] = []
    total_chars = 0

    for doc_id in document_ids:
        if total_chars >= MAX_TOTAL_CHARS:
            break

        doc = docs_by_id.get(doc_id)
        if doc is None:
            attached.append(
                {
                    "filename": doc_id,
                    "text": "[Документ не найден или недоступен]",
                }
            )
            continue

        file_path = doc.file_path
        if not file_path:
            attached.append(
                {
                    "filename": doc.title,
                    "text": "[Файл документа отсутствует на сервере]",
                }
            )
            continue

        path = Path(file_path)
        if not path.is_file():
            attached.append(
                {
                    "filename": doc.title,
                    "text": "[Файл документа не найден на диске]",
                }
            )
            continue

        try:
            raw_text = extract_text_from_file(path)
        except Exception as exc:
            attached.append(
                {
                    "filename": doc.title,
                    "text": f"[Не удалось извлечь текст: {exc}]",
                }
            )
            continue

        remaining = MAX_TOTAL_CHARS - total_chars
        if remaining <= 0:
            break

        text = truncate_text(raw_text, min(MAX_DOC_CHARS, remaining))
        if not text:
            attached.append(
                {
                    "filename": doc.title,
                    "text": "[Документ не содержит извлекаемого текста]",
                }
            )
            continue

        total_chars += len(text)
        attached.append({"filename": doc.title, "text": text})

    return attached


__all__ = ["load_user_documents_text"]
