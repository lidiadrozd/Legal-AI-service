"""Rasterize actual Word exports; create contact sheets for visual inspection."""
from pathlib import Path
import json
from pdf2image import convert_from_path
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parents[1] / "artifacts/document_templates_2026-10-24_fixed/qa"
pages = []
for path in sorted(root.glob("*.pdf")):
    rendered = convert_from_path(path, dpi=100)
    for index, page in enumerate(rendered, 1):
        name = f"{path.stem}-page-{index}.png"
        page.save(root / name)
        pages.append((path.stem, index, page))
for start in range(0, len(pages), 4):
    sheet = Image.new("RGB", (1654, 2400), "#dddddd")
    for position, (name, number, page) in enumerate(pages[start:start+4]):
        x, y = (position % 2) * 827, (position // 2) * 1200
        sheet.paste(page, (x, y+28))
        ImageDraw.Draw(sheet).text((x+5, y+5), f"{name} page {number}", fill="black")
    sheet.save(root / f"final-contact-{start//4+1}.png")
print(json.dumps({"pdf_count": len(list(root.glob('*.pdf'))), "page_count": len(pages), "contact_sheets": (len(pages)+3)//4}))
