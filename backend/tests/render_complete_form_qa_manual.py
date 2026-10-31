"""Production LibreOffice conversion of already authored factual QA DOCX files."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from io import BytesIO
import json
from pypdf import PdfReader
from app.services.document_docx_template import docx_to_pdf

ROOT=Path(__file__).parent/'complete-forms-qa'


def convert(path):
    data=docx_to_pdf(path.read_bytes());reader=PdfReader(BytesIO(data))
    text='\n'.join(p.extract_text() or '' for p in reader.pages)
    assert '{{' not in text and 'Source_text' not in text,path.name
    assert all(len((page.extract_text() or '').strip())>30 for page in reader.pages),path.name
    path.with_suffix('.pdf').write_bytes(data)
    print(path.stem,len(reader.pages),flush=True)
    return dict(scenario=path.stem,pages=len(reader.pages))


if __name__=='__main__':
    with ThreadPoolExecutor(max_workers=2) as pool:report=list(pool.map(convert,sorted(ROOT.glob('*.docx'))))
    (ROOT/'pdf-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
