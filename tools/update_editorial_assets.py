"""Version consumer refund wrappers without changing legal rules or old assets."""
import json
from pathlib import Path
from types import SimpleNamespace
from build_catalog_docx_assets import build

ROOT=Path(__file__).resolve().parents[1]/'backend/app/templates'
KEYS={'pretense_consumer_late_delivery','pretense_consumer_defective_goods',
      'pretense_consumer_defective_service','claim_consumer'}


def main():
    versions={}
    for key in sorted(KEYS):
        path=ROOT/'documents'/f'{key}.json'
        package=json.loads(path.read_text(encoding='utf-8'))
        old='Исполнение денежного требования и направление ответа: {{payment}}.'
        if not any(block['text']==old for block in package['blocks']):continue
        for block in package['blocks']:
            if block['text']==old:block['text']='Способ возврата денежных средств: {{payment}}.'
        package['version']+=1
        intake=json.loads((ROOT/'intake'/f'{key}.json').read_text(encoding='utf-8'))
        scenario=SimpleNamespace(key=key,fields=[SimpleNamespace(**f) for f in intake['fields']])
        build(key,scenario,package)
        versions[key]=package['version']
        print(key,package['version'])
    catalog_path=ROOT/'catalog40.json'
    catalog=json.loads(catalog_path.read_text(encoding='utf-8'))
    for row in catalog['forms']:
        if row['scenario'] in versions:row['version']=versions[row['scenario']]
    catalog_path.write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
