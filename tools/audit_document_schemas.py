"""Inventory structural coverage without confusing it with legal review."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.services.document_schema import catalog_audit
from app.services.document_scenarios import SCENARIOS
from app.services.document_template_library import load_text_package, PLACEHOLDER

rows = catalog_audit()
for row in rows:
    scenario = SCENARIOS[row['scenario']]
    package = load_text_package(scenario)
    used = set(PLACEHOLDER.findall('\n'.join(b['text'] for b in package['blocks'])))
    row['intake_fields_without_direct_output'] = [f.key for f in scenario.fields if f.key not in used]
    row['conditional_fields'] = [f.key for f in scenario.fields if f.when_field]
target = ROOT / 'docs/document_schema_audit.json'
target.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'scenarios': len(rows), 'structured': sum(r['coverage'] == 'structured' for r in rows),
    'basic': sum(r['coverage'] == 'basic' for r in rows), 'invalid': [r['scenario'] for r in rows if r['issues']]}, ensure_ascii=False))
if any(r['issues'] for r in rows): raise SystemExit(1)
