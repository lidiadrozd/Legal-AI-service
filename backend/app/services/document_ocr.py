"""
OCR для фото и сканированных PDF (Tesseract).
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


def is_image_file(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_SUFFIXES


def is_tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def _ocr_pil_image(image: Image.Image, *, lang: str) -> str:
    import pytesseract

    rgb = image.convert("RGB")
    return pytesseract.image_to_string(rgb, lang=lang).strip()


def ocr_image(path: Path, *, lang: str) -> str:
    if not is_tesseract_available():
        raise RuntimeError(
            "OCR недоступен на сервере. Установите Tesseract или загрузите PDF/DOCX/TXT с текстовым слоем."
        )

    with Image.open(path) as image:
        return _ocr_pil_image(image, lang=lang)


def ocr_pdf_pages(path: Path, *, lang: str, max_pages: int) -> str:
    if not is_tesseract_available():
        raise RuntimeError(
            "OCR недоступен на сервере. Установите Tesseract или загрузите PDF с текстовым слоем."
        )

    import fitz

    doc = fitz.open(str(path))
    parts: list[str] = []
    try:
        total_pages = len(doc)
        pages_to_process = min(total_pages, max_pages)
        for page_index in range(pages_to_process):
            page = doc.load_page(page_index)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            text = _ocr_pil_image(image, lang=lang)
            if text:
                parts.append(text)

        if total_pages > max_pages:
            parts.append(f"...[распознано {pages_to_process} из {total_pages} страниц]")
    finally:
        doc.close()

    return "\n\n".join(parts).strip()


__all__ = [
    "IMAGE_SUFFIXES",
    "is_image_file",
    "is_tesseract_available",
    "ocr_image",
    "ocr_pdf_pages",
]
