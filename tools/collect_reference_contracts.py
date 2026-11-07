"""Publicly offered blank DOCX forms, retained as internal source references.

Public download is not recorded as a license to republish an author's forms.
Executable adapters remain independently authored and versioned separately.
"""
from hashlib import sha256
from io import BytesIO
import json
from docx import Document
from collect_public_document_forms import ROOT, get

TYPES = {
    'lease': ('Договор найма жилого помещения', ['contract_housing']),
    'sale': ('Договор купли-продажи квартиры', []),
    'preliminary': ('Предварительный договор купли-продажи', []),
    'deposit_agreement': ('Договор задатка', []),
    'gift': ('Договор дарения квартиры', []),
    'act_transfer': ('Акт приёма-передачи квартиры', []),
    'receipt': ('Расписка в получении денежных средств', []),
    'sale_land': ('Договор купли-продажи земельного участка', []),
}

path = ROOT / 'manifest.json'
rows = {r['id']: r for r in json.loads(path.read_text(encoding='utf-8'))}
for kind, (title, scenarios) in TYPES.items():
    url = 'https://arrj.ru/obrazec?type=' + kind
    try:
        raw = get(url)
        if not raw.startswith(b'PK'): raise ValueError('The endpoint did not return DOCX')
        doc = Document(BytesIO(raw))
        text = '\n\n'.join([p.text for p in doc.paragraphs] + [' | '.join(c.text for c in row.cells) for table in doc.tables for row in table.rows]).strip()
        if len(text) < 200: raise ValueError('Incomplete source')
        identity = sha256(raw).hexdigest(); key = 'contract-' + identity[:16]
        (ROOT/'raw'/(key+'.docx')).write_bytes(raw)
        (ROOT/'text'/(key+'.txt')).write_bytes(text.encode('utf-8'))
        rows[key] = dict(id=key,title=title,publisher='ARRJ — публичные ознакомительные бланки',source_url=url,
            source_page='https://arrj.ru/shablony',raw_path='raw/'+key+'.docx',text_path='text/'+key+'.txt',
            sha256=identity,text_sha256=sha256(text.encode()).hexdigest(),characters=len(text),
            downloaded_at='2026-10-25',source_revision='not_verified',use='internal_structure_reference',
            document_kind='act' if kind=='act_transfer' else ('receipt' if kind=='receipt' else 'contract'),
            scenarios=scenarios,material_type='blank_form',
            usage_basis='Публично предлагаемый ознакомительный бланк. Право перепубликации оригинала не подтверждено; хранится для внутренней структурной сверки. Выдаваемая форма — самостоятельная редакция.',
            review_status='requires_current_law_and_field_mapping_review')
        print('DOWNLOADED', kind, len(text), flush=True)
    except Exception as error: print('FAILED', kind, type(error).__name__, flush=True)
path.write_text(json.dumps(sorted(rows.values(),key=lambda r:r['id']),ensure_ascii=False,indent=2),encoding='utf-8')
print('TOTAL',len(rows))
