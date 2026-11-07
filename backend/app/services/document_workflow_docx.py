"""Deterministic legal-document layout shared by app exports and sample artifacts."""
from io import BytesIO
import re
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.shared import Cm, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn


def layout_blocks(blocks):
    """Real paragraphs wrap and paginate; a body is not one manual-break run."""
    for block in blocks:
        role = block.get("role", "body")
        lines = [line.strip() for line in block["text"].splitlines() if line.strip()]
        if role == "attachments" and len(lines) > 1:
            lines = [line if re.match(r"^\d+[.)]\s", line) else f"{i}. {line}"
                     for i, line in enumerate(lines, 1)]
        if role in {"body", "request", "attachments"}:
            yield from ({**block, "text": line} for line in lines)
        else:
            yield {**block, "text": "\n".join(lines)}


def build_legal_docx(title: str, blocks: list[dict], *, review_note: str = "") -> bytes:
    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.top_margin, section.bottom_margin = Cm(2), Cm(2)
    section.left_margin, section.right_margin = Cm(3), Cm(1.5)
    for name in ("Normal", "Title", "Heading 1", "Heading 2"):
        style = doc.styles[name]
        style.font.name = "Times New Roman"
        style.font.size = Pt(12)
        style.font.color.rgb = RGBColor(0, 0, 0)
        fonts = style.element.get_or_add_rPr().get_or_add_rFonts()
        for attr in list(fonts.attrib):
            if "theme" in attr.lower(): del fonts.attrib[attr]
        for attr in ("ascii", "hAnsi", "cs", "eastAsia"):
            fonts.set(qn("w:" + attr), "Times New Roman")
        for border in style.element.findall(".//" + qn("w:pBdr")):
            border.getparent().remove(border)
    normal = doc.styles["Normal"].paragraph_format
    normal.line_spacing = 1.15
    normal.space_after = Pt(4)
    normal.widow_control = True
    doc.core_properties.title = title
    doc.core_properties.subject = "Шаблон юридического документа с полями для заполнения"
    for block in layout_blocks(blocks):
        role = block.get("role", "body")
        paragraph = doc.add_paragraph(style="Title" if role == "title" else "Heading 1" if role == "heading" else "Normal")
        paragraph.paragraph_format.keep_with_next = role in {"title", "heading", "attachments"}
        paragraph.paragraph_format.first_line_indent = Cm(1.25) if role in {"body", "request"} else Cm(0)
        paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY if role in {"body", "request"} else WD_ALIGN_PARAGRAPH.LEFT
        if role == "addressee":
            paragraph.paragraph_format.left_indent = Cm(8)
            paragraph.paragraph_format.space_after = Pt(3)
        if role == "title":
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            paragraph.paragraph_format.space_before = Pt(8)
            paragraph.paragraph_format.space_after = Pt(8)
        if role == "heading":
            paragraph.paragraph_format.space_before = Pt(8)
            paragraph.paragraph_format.space_after = Pt(4)
        if role == "signature":
            paragraph.paragraph_format.space_before = Pt(10)
            paragraph.paragraph_format.keep_together = True
        if role == "place_date":
            paragraph.paragraph_format.keep_with_next = True
            if '\t' in block['text']:
                paragraph.paragraph_format.tab_stops.add_tab_stop(section.page_width-section.left_margin-section.right_margin,WD_TAB_ALIGNMENT.RIGHT)
        if role == "attachments":
            paragraph.paragraph_format.left_indent = Cm(0.6)
            paragraph.paragraph_format.first_line_indent = Cm(-0.6)
        for i, line in enumerate(block["text"].split("\n")):
            if i: paragraph.add_run().add_break()
            run = paragraph.add_run(line)
            run.font.name = "Times New Roman"
            run.font.size = Pt(14 if role=='title' else 12)
            run.bold = role in {"title", "heading"}
    # Legal templates normally do not need a visible number on page one.
    # ГОСТ Р 7.0.97-2025 places later page numbers in the upper field,
    # 10 mm from the top edge.
    section.different_first_page_header_footer = True
    section.header_distance = Cm(1)
    header = section.header.paragraphs[0]
    header.alignment = WD_ALIGN_PARAGRAPH.CENTER
    header.paragraph_format.space_before = Pt(0)
    header.paragraph_format.space_after = Pt(0)
    header_run = header.add_run()
    header_run.font.name = "Times New Roman"
    header_run.font.size = Pt(12)
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    header_run._r.addnext(field)

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if review_note:
        run = footer.add_run(review_note + "\n")
        run.font.name = "Times New Roman"
        run.font.size = Pt(9)
    output = BytesIO()
    doc.save(output)
    return output.getvalue()


def build_legal_pdf(title: str, blocks: list[dict], *, review_note: str = "") -> bytes:
    from html import escape
    from pathlib import Path
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph
    fonts = [("LegalSerif", "C:/Windows/Fonts/times.ttf", "C:/Windows/Fonts/timesbd.ttf"),
             ("LegalSerif", "/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf", "/usr/share/fonts/truetype/liberation2/LiberationSerif-Bold.ttf"),
             ("LegalSerif", "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf")]
    selected = next(((name, regular, bold) for name, regular, bold in fonts if Path(regular).is_file() and Path(bold).is_file()), None)
    if selected is None:
        raise RuntimeError("Не найден шрифт с кириллицей для PDF. Используйте DOCX или установите Liberation Serif.")
    name, regular, bold = selected
    pdfmetrics.registerFont(TTFont(name, regular))
    pdfmetrics.registerFont(TTFont(name + "Bold", bold))
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, leftMargin=30*mm, rightMargin=15*mm,
                            topMargin=20*mm, bottomMargin=25*mm, title=title)
    styles = {
        "body": ParagraphStyle("Body", fontName=name, fontSize=14, leading=16.1, firstLineIndent=12.5*mm, alignment=TA_JUSTIFY, spaceAfter=6),
        "addressee": ParagraphStyle("Addressee", fontName=name, fontSize=14, leading=16.1, leftIndent=80*mm, spaceAfter=3),
        "title": ParagraphStyle("Title", fontName=name+"Bold", fontSize=14, leading=17, alignment=TA_CENTER, spaceBefore=12, spaceAfter=12, keepWithNext=True),
        "heading": ParagraphStyle("Heading", fontName=name+"Bold", fontSize=14, leading=17, spaceBefore=8, spaceAfter=4, keepWithNext=True),
        "plain": ParagraphStyle("Plain", fontName=name, fontSize=14, leading=16.1, spaceAfter=6),
    }
    styles["place_date"] = ParagraphStyle("Date", parent=styles["plain"], keepWithNext=True)
    styles['request'] = ParagraphStyle('Request', parent=styles['body'])
    flow = [Paragraph(escape(block["text"]).replace("\n", "<br/>"), styles.get(block.get("role"), styles["plain"])) for block in layout_blocks(blocks)]
    def footer(canvas, document):
        canvas.setFont(name, 8)
        if review_note: canvas.drawCentredString(A4[0]/2, 14*mm, review_note)
        if document.page > 1:
            canvas.drawCentredString(A4[0]/2, A4[1]-10*mm, str(document.page))
    doc.build(flow, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
