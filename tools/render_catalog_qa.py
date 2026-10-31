"""Render all converted pages and a numbered layout review contact sheet."""
import json
from pathlib import Path
import pypdfium2 as pdfium
from PIL import Image,ImageOps,ImageDraw

root=Path(__file__).resolve().parents[1]
source=root/'backend/tests/catalog40-qa'
out=root/'artifacts/catalog40-review';out.mkdir(exist_ok=True)
pages=[]
for row in json.loads((source/'report.json').read_text(encoding='utf-8')):
    key=row['scenario'];pdf=pdfium.PdfDocument(source/(key+'.pdf'))
    for number,page in enumerate(pdf):
        picture=page.render(scale=1.5).to_pil().convert('RGB')
        picture.save(out/f'{key}-{number+1}.png')
        pages.append((f'{key} / {number+1}',picture))
for start in range(0,len(pages),4):
    canvas=Image.new('RGB',(1300,1900),'#dddddd');draw=ImageDraw.Draw(canvas)
    for offset,(label,picture) in enumerate(pages[start:start+4]):
        thumb=ImageOps.contain(picture,(630,900))
        x=10+(offset%2)*650;y=20+(offset//2)*950
        draw.text((x,y),label,fill='black');canvas.paste(thumb,(x,y+25))
    canvas.save(out/f'sheet-{start//4+1:02}.png')
print('Rendered all pages:',len(pages),'review sheets:',(len(pages)+3)//4)
