"""Explicit source-to-purpose links; no nearest-template assignments."""
from pathlib import Path
import json
root=Path(__file__).resolve().parents[1]/'backend/app/templates/form_sources'
mapping={
    'court-2ab8a3ec00e380d2':['claim_labor_salary'],
    'court-8528825ba35ae0a3':['claim_labor_reinstatement'],
    'court-548c5581d752afde':['claim_alimony_share'],
    'court-db6189c7b07df250':['claim_divorce'],
    'court-b43f77886ac7dd51':['pretense_consumer_defective_service','claim_consumer'],
    'court-d6127cf43b5e03c3':['pretense_consumer_defective_goods','claim_consumer'],
    'court-9b044e18dcbdc330':['pretense_labor_settlement'],
}
path=root/'manifest.json';rows=json.loads(path.read_text(encoding='utf-8'))
for row in rows:
    if row['id'] in mapping:
        row['scenarios']=sorted(set(row.get('scenarios',[])+mapping[row['id']]))
path.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
print('Additional explicit source mappings:',len(mapping))
