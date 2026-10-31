"""Rasterize every audited Word export and create two-page review sheets."""
import json
from pathlib import Path
import pypdfium2 as pdfium
from PIL import Image,ImageOps,ImageDraw
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/catalog-audit-2026-10-29';PAGES=OUT/'pages';PAGES.mkdir(exist_ok=True)
rows=json.loads((OUT/'layout-report.json').read_text(encoding='utf-8'));pictures=[]
for row in rows:
    key=row['scenario'];source=ROOT/'artifacts/layout-qa'/(key+'.pdf')
    pdf=pdfium.PdfDocument(source);row['pages']=len(pdf)
    row['pdf_text_bounds']=[]
    for i,page in enumerate(pdf):
        picture=page.render(scale=1.5).to_pil().convert('RGB');picture.save(PAGES/f'{key}-{i+1}.png')
        pictures.append((f'{key} / {i+1}',picture))
        text=page.get_textpage()
        boxes=[text.get_charbox(n) for n in range(text.count_chars()) if text.get_text_range(n,1).strip()]
        if boxes:row['pdf_text_bounds'].append(dict(left=round(min(b[0] for b in boxes),1),bottom=round(min(b[1] for b in boxes),1),right=round(max(b[2] for b in boxes),1),top=round(max(b[3] for b in boxes),1)))
        text.close()
    pdf.close()
for start in range(0,len(pictures),2):
    sheet=Image.new('RGB',(1800,1320),'#e5e5e5');draw=ImageDraw.Draw(sheet)
    for offset,(label,picture) in enumerate(pictures[start:start+2]):
        thumb=ImageOps.contain(picture,(875,1260));x=15+900*offset
        draw.text((x,10),label,fill='black');sheet.paste(thumb,(x,35))
    sheet.save(PAGES/f'sheet-{start//2+1:02}.png')
(OUT/'layout-report.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(documents=len(rows),pages=len(pictures),sheets=(len(pictures)+1)//2)))
