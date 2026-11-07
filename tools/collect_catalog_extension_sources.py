"""Add family/procedural originals without overwriting existing source mappings."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from hashlib import sha256
import json
from urllib.parse import urljoin,urlparse
from collect_public_document_forms import ROOT,COURT,page,get,pdf_text

pages=[COURT+'/index.php/spravochnaya-informatsiya/poryadok-obrashcheniya-v-sud/'+slug for slug in [
    '1448-obraztsy-iskovykh-zayavlenij-o-zashchite-semejnykh-prav',
    '1451-obraztsy-iskovykh-zayavlenij-o-zashchite-trudovykh-prav',
    '1494-obraztsy-inykh-dokumentov-otnosyashchikhsya-k-rassmotreniyu-del-v-grazhdanskom-proizvodstve']]
manifest=ROOT/'manifest.json';rows=json.loads(manifest.read_text(encoding='utf-8'))
known={row['source_url'] for row in rows};candidates=[]
for location in pages:
    for href,label in page(location).links:
        url=urljoin(location,href)
        if urlparse(url).hostname=='nnoblsud.ru' and urlparse(url).path.lower().endswith('.pdf') and url not in known:
            candidates.append((url,label,location));known.add(url)
def download(item):
    url,label,location=item
    try:
        raw=get(url)
        if not raw.startswith(b'%PDF'): return None
        extracted=pdf_text(raw);digest=sha256(raw).hexdigest();identity='court-'+digest[:16]
        (ROOT/'raw'/f'{identity}.pdf').write_bytes(raw)
        (ROOT/'text'/f'{identity}.txt').write_bytes(extracted.encode('utf-8'))
        return dict(id=identity,title=label,publisher='Нижегородский областной суд',source_url=url,source_page=location,
            raw_path=f'raw/{identity}.pdf',text_path=f'text/{identity}.txt',sha256=digest,
            text_sha256=sha256(extracted.encode('utf-8')).hexdigest(),characters=len(extracted),
            downloaded_at=date.today().isoformat(),source_revision='not_verified',use='reference_only',
            usage_basis='Публичный образец официального суда; авторская адаптация хранится отдельно.',
            review_status='requires_current_law_and_field_mapping_review',document_kind='claim',scenarios=[],executable=False)
    except Exception as error:
        print('SOURCE_FAILED',type(error).__name__,flush=True);return None
with ThreadPoolExecutor(max_workers=5) as pool:
    added=[row for row in pool.map(download,candidates) if row]
by_id={row['id']:row for row in rows}
for row in added: by_id.setdefault(row['id'],row)
manifest.write_text(json.dumps(list(by_id.values()),ensure_ascii=False,indent=2),encoding='utf-8')
print('Source documents:',len(by_id),'downloaded in this pass:',len(added),flush=True)
