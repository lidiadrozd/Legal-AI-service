"""Explicit source-to-scenario mappings. Similar subject matter is not a mapping."""
import json
from hashlib import sha256
from pathlib import Path

root = Path(__file__).resolve().parents[1] / 'backend/app/templates/form_sources'
path = root/'manifest.json'
rows = json.loads(path.read_text(encoding='utf-8'))
MAPPINGS = {
    'court-9d1757713bacc473': ['claim_damage_flood'],
    'court-6874032de7055971': ['claim_damage_property'],
    'court-b2815074068636de': ['claim_consumer'],
    'court-cd25c1d959e2cd18': ['claim_consumer'],
    'court-d6127cf43b5e03c3': ['claim_consumer'],
    'court-1fb9feda65733ec3': ['claim_consumer'],
    'court-b43f77886ac7dd51': ['claim_consumer'],
    'contract-98857741b4e2866b': ['contract_housing'],
}
for row in rows:
    text_file=root/row['text_path']
    raw=text_file.read_bytes()
    # Older Windows writes translated LF to CRLF after hashing the string.
    # Repair only this proven encoding difference, never accept changed text.
    if sha256(raw).hexdigest()!=row['text_sha256'] and sha256(raw.replace(b'\r\n',b'\n')).hexdigest()==row['text_sha256']:
        text_file.write_bytes(raw.replace(b'\r\n',b'\n'))
    if row['publisher'] == 'Нижегородский областной суд':
        row['document_kind'] = 'claim'
        row['material_type'] = 'blank_form'
    row['scenarios'] = MAPPINGS.get(row['id'], [])
    row['executable'] = False
    row['mapping_note'] = 'Только справочная структура; действующие нормы и условия проверяются отдельно. Автозаполнение выполняется по собственной версии схемы.'
path.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
print('Sources:',len(rows),'Mapped references:',sum(bool(row['scenarios']) for row in rows))
