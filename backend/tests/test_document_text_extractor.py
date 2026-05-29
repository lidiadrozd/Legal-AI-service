from io import BytesIO
from pathlib import Path

import pytest
from docx import Document as DocxBuilder
from PIL import Image, ImageDraw
from reportlab.pdfgen import canvas

from app.core.prompts import format_chat_context
from app.services.document_ocr import is_tesseract_available
from app.services.document_text_extractor import extract_text_from_file, truncate_text


def test_truncate_text_adds_suffix():
    result = truncate_text("a" * 20, 10)
    assert result.startswith("a" * 10)
    assert result.endswith("...[текст обрезан]")


def test_extract_text_from_txt(tmp_path: Path):
    path = tmp_path / "note.txt"
    path.write_text("Договор аренды", encoding="utf-8")
    assert extract_text_from_file(path) == "Договор аренды"


def test_extract_text_from_docx(tmp_path: Path):
    buf = BytesIO()
    doc = DocxBuilder()
    doc.add_paragraph("Претензия по ст. 720 ГК РФ")
    doc.save(buf)

    path = tmp_path / "claim.docx"
    path.write_bytes(buf.getvalue())
    assert "Претензия" in extract_text_from_file(path)


def test_extract_text_from_pdf(tmp_path: Path):
    path = tmp_path / "scan.pdf"
    pdf = canvas.Canvas(str(path))
    pdf.drawString(72, 800, "Claim document text")
    pdf.save()

    extracted = extract_text_from_file(path)
    assert "Claim document text" in extracted


@pytest.mark.skipif(not is_tesseract_available(), reason="Tesseract OCR is not installed")
def test_extract_text_from_image(tmp_path: Path):
    path = tmp_path / "scan.png"
    image = Image.new("RGB", (640, 120), color="white")
    draw = ImageDraw.Draw(image)
    draw.text((20, 40), "Contract clause 12", fill="black")
    image.save(path)

    extracted = extract_text_from_file(path)
    assert "Contract" in extracted or "clause" in extracted


def test_extract_image_without_tesseract_raises(monkeypatch, tmp_path: Path):
    path = tmp_path / "photo.png"
    Image.new("RGB", (32, 32), color="white").save(path)

    monkeypatch.setattr(
        "app.services.document_text_extractor.is_tesseract_available",
        lambda: False,
    )

    with pytest.raises(ValueError, match="OCR недоступен"):
        extract_text_from_file(path)


def test_format_chat_context_includes_attached_documents():
    context = {
        "docs": ["Изменение: Налоговый кодекс"],
        "law_db_size": 12,
        "attached_documents": [
            {"filename": "contract.pdf", "text": "Стороны: ООО Ромашка и Иванов И.И."},
        ],
    }
    rendered = format_chat_context(context)
    assert "Прикреплённые документы пользователя" in rendered
    assert "=== contract.pdf ===" in rendered
    assert "ООО Ромашка" in rendered
    assert "Изменение: Налоговый кодекс" in rendered
