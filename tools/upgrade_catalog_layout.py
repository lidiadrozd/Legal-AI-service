"""Versioned OOXML repair preserving native signature tables and all controls."""
import json,re,hashlib
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from lxml import etree
ROOT=Path(__file__).resolve().parents[1]/'backend/app/templates'
W='http://schemas.openxmlformats.org/wordprocessingml/2006/main';NS={'w':W}
def tag(name):return '{'+W+'}'+name
def main():
    catalog_path=ROOT/'catalog40.json';catalog=json.loads(catalog_path.read_text(encoding='utf-8'))
    for row in catalog['forms']:
        key=row['scenario'];path=ROOT/'documents'/f'{key}.json';package=json.loads(path.read_text(encoding='utf-8'))
        old=package['docx_asset'];source=ROOT/'assets'/old['template'];schema=json.loads((ROOT/'assets'/old['schema']).read_text(encoding='utf-8'))
        for block in package['blocks']:
            if block.get('role')=='place_date' and '{{place}}' in block['text'] and '{{date}}' in block['text']:
                block['text']=re.sub(r'\}\}[ \t]+\{\{','}}\t{{',block['text'])
        package['version']+=1;out=ROOT/'assets'/key/f"v{package['version']}";out.mkdir(exist_ok=False)
        with ZipFile(source) as zin,ZipFile(out/'template.docx','w',ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data=zin.read(item.filename)
                if item.filename=='word/document.xml':
                    root=etree.fromstring(data);sect=root.find('.//w:sectPr',NS)
                    size=sect.find('w:pgSz',NS);margin=sect.find('w:pgMar',NS)
                    width=int(size.get(tag('w')))-int(margin.get(tag('left')))-int(margin.get(tag('right')))
                    for p in root.findall('.//w:p',NS):
                        names=p.xpath('.//w:sdtPr/w:tag/@w:val',namespaces=NS)
                        if 'field:place' not in names or 'field:date' not in names:continue
                        pr=p.find('w:pPr',NS)
                        if pr is None:pr=etree.Element(tag('pPr'));p.insert(0,pr)
                        tabs=pr.find('w:tabs',NS)
                        if tabs is None:tabs=etree.SubElement(pr,tag('tabs'))
                        for child in list(tabs):tabs.remove(child)
                        tab=etree.SubElement(tabs,tag('tab'));tab.set(tag('val'),'right');tab.set(tag('pos'),str(width))
                        for name in ('keepNext','keepLines'):
                            element=pr.find('w:'+name,NS)
                            if element is None:element=etree.SubElement(pr,tag(name))
                            element.set(tag('val'),'1')
                        for run in p.findall('w:r',NS):
                            for t in list(run.findall('w:t',NS)):
                                if (t.text or '') and not (t.text or '').strip():
                                    run.remove(t);etree.SubElement(run,tag('tab'))
                    data=etree.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
                zout.writestr(item,data)
        schema['version']=package['version'];schema['blocks_sha256']=hashlib.sha256(json.dumps(package['blocks'],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        (out/'schema.json').write_text(json.dumps(schema,ensure_ascii=False,indent=2),encoding='utf-8')
        package['docx_asset']={name:str((out/filename).relative_to(ROOT/'assets')).replace('\\','/') for name,filename in [('template','template.docx'),('schema','schema.json')]}
        for name in ('template','schema'):package['docx_asset'][name+'_sha256']=hashlib.sha256((ROOT/'assets'/package['docx_asset'][name]).read_bytes()).hexdigest()
        path.write_text(json.dumps(package,ensure_ascii=False,indent=2),encoding='utf-8');row['version']=package['version']
        print(key,package['version'])
    catalog['revision']='2026-10-29';catalog_path.write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
