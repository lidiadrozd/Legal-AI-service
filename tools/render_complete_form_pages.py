"""Render every production PDF page plus contact sheets for layout review."""
import json
from pathlib import Path
import pypdfium2 as pdfium
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'backend/tests/complete-forms-qa'
OUT=ROOT/'artifacts/complete-forms-review';OUT.mkdir(exist_ok=True)
pages=[]
for row in json.loads((SOURCE/'pdf-report.json').read_text(encoding='utf-8')):
    pdf=pdfium.PdfDocument(SOURCE/(row['scenario']+'.pdf'))
    for n,page in enumerate(pdf):
        picture=page.render(scale=1.5).to_pil().convert('RGB')
        picture.save(OUT/f"{row['scenario']}-{n+1}.png")
        pages.append((f"{row['scenario']} / {n+1}",picture))
for start in range(0,len(pages),4):
    canvas=Image.new('RGB',(1840,2640),'#dddddd');draw=ImageDraw.Draw(canvas)
    for n,(label,picture) in enumerate(pages[start:start+4]):
        x=10+(n%2)*920;y=10+(n//2)*1320
        draw.text((x,y),label,fill='black');canvas.paste(picture,(x,y+25))
    canvas.save(OUT/f'sheet-{start//4+1:02}.png')
print('Pages rendered:',len(pages),'sheets:',(len(pages)+3)//4)
