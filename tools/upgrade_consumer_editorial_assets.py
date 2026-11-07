"""Render delivery deadlines as complete prose, retaining immutable old assets."""
import json
from pathlib import Path
from types import SimpleNamespace
from build_catalog_docx_assets import build
ROOT=Path(__file__).resolve().parents[1]/'backend/app/templates'

def main():
    versions={}
    for key in ('pretense_consumer_late_delivery','pretense_consumer_defective_goods','pretense_consumer_defective_service'):
        path=ROOT/'documents'/f'{key}.json';package=json.loads(path.read_text(encoding='utf-8'))
        changed=False
        for block in package['blocks']:
            if block['text']=='Сторонами был согласован следующий срок передачи товара: {{delivery_due}}.':
                block['text']='{{delivery_due}}';package['field_formats']['delivery_due']='sentence';changed=True
            if block['text']=='Приобретение осуществлялось для следующих целей: {{consumer_status}}.':
                block['text']=('Услуги заказаны' if key.endswith('service') else 'Товар приобретён')+' для {{consumer_status}}.';changed=True
        if not changed:continue
        package['version']+=1
        intake=json.loads((ROOT/'intake'/f'{key}.json').read_text(encoding='utf-8'))
        build(key,SimpleNamespace(key=key,fields=[SimpleNamespace(**f) for f in intake['fields']]),package)
        versions[key]=package['version']
        print(key,package['version'])
    path=ROOT/'catalog40.json';catalog=json.loads(path.read_text(encoding='utf-8'))
    for row in catalog['forms']:
        if row['scenario'] in versions:row['version']=versions[row['scenario']]
    path.write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
