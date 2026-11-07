"""Download public source forms, never turn an unreviewed download into a live template."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlparse, quote, unquote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1] / 'backend/app/templates/form_sources'
COURT = 'https://nnoblsud.ru'


class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links = []; self.parts = []; self.href = None; self.label = []; self.heading = ''; self.in_heading = False
    def handle_starttag(self, tag, attrs):
        if tag in {'h2', 'h3'}: self.heading = ''; self.in_heading = True
        if tag == 'a': self.href = dict(attrs).get('href'); self.label = []
    def handle_data(self, data):
        self.parts.append(data)
        if self.in_heading: self.heading += data
        if self.href: self.label.append(data)
    def handle_endtag(self, tag):
        if tag in {'h2', 'h3'}: self.in_heading = False
        if tag == 'a' and self.href:
            label = ' '.join(self.label).strip()
            self.links.append((self.href, self.heading.strip() if label.upper() in {'PDF', 'DOC'} else label)); self.href = None


def get(url):
    p = urlparse(url)
    if p.scheme != 'https' or p.hostname not in {'nnoblsud.ru', 'zpp.rospotrebnadzor.ru', 'xn--80aald4bq.xn--d1aqf.xn--p1ai', 'arrj.ru'}:
        raise ValueError('Unapproved source domain')
    url = p._replace(path=quote(unquote(p.path), safe='/,:-._')).geturl()
    with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0 LegalFormLibrary/1.0'}), timeout=18) as response:
        raw = response.read(15_000_001)
        if len(raw) > 15_000_000: raise ValueError('Source too large')
        return raw


def page(url):
    raw = get(url)
    try: text = raw.decode('utf-8')
    except UnicodeDecodeError: text = raw.decode('cp1251')
    parser = Links(); parser.feed(text); return parser


def pdf_text(raw):
    from io import BytesIO
    from pypdf import PdfReader
    return '\n\n'.join(p.extract_text() or '' for p in PdfReader(BytesIO(raw)).pages).strip()


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / 'raw').mkdir(exist_ok=True); (ROOT / 'text').mkdir(exist_ok=True)
    landing = [COURT + '/index.php/spravochnaya-informatsiya?limit=100',
        COURT + '/index.php/spravochnaya-informatsiya/51-spravochnaya-informatsiya?start=50',
        COURT + '/index.php/spravochnaya-informatsiya/poryadok-obrashcheniya-v-sud/1451-obraztsy-iskovykh-zayavlenij-o-zashchite-trudovykh-prav',
        COURT + '/index.php/spravochnaya-informatsiya/poryadok-obrashcheniya-v-sud/1494-obraztsy-inykh-dokumentov-otnosyashchikhsya-k-rassmotreniyu-del-v-grazhdanskom-proizvodstve',
        COURT + '/index.php/spravochnaya-informatsiya/51-spravochnaya-informatsiya/1454-obraztsy-iskovykh-zayavlenij-o-vozmeshchenii-ushcherba']
    pages = set(landing)
    for url in landing:
        try:
            for href, title in page(url).links:
                target = urljoin(url, href)
                if urlparse(target).hostname == 'nnoblsud.ru' and re.search(r'образц|заявлен|ходатайств|жалоб', title, re.I): pages.add(target)
        except Exception as error: print('PAGE_FAILED', type(error).__name__, url, flush=True)
    def discover(url):
        try:
            found = []
            for href, label in page(url).links:
                target = urljoin(url, href)
                if urlparse(target).hostname == 'nnoblsud.ru' and urlparse(target).path.lower().endswith('.pdf') and '/forms/' in target:
                    found.append((target, url, label))
            return found
        except Exception: return []
    files = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        for found in pool.map(discover, sorted(pages)):
            for item in found: files[item[0]] = item
    print('PAGES', len(pages), 'DISCOVERED', len(files), flush=True)
    def download(item):
        url, source_page, label = item
        try:
            raw = get(url)
            if not raw.startswith(b'%PDF'): raise ValueError('Not a PDF')
            text = pdf_text(raw)
            identity = sha256(raw).hexdigest()
            key = 'court-' + identity[:16]
            (ROOT / 'raw' / (key + '.pdf')).write_bytes(raw)
            (ROOT / 'text' / (key + '.txt')).write_bytes(text.encode('utf-8'))
            return {'id': key, 'source_url': url, 'source_page': source_page, 'publisher': 'Нижегородский областной суд',
                'title': label or unquote(urlparse(url).path.rsplit('/', 1)[-1]).removesuffix('.pdf'),
                'raw_path': 'raw/' + key + '.pdf', 'text_path': 'text/' + key + '.txt',
                'sha256': identity, 'text_sha256': sha256(text.encode()).hexdigest(), 'characters': len(text),
                'downloaded_at': '2026-10-25', 'source_revision': 'not_verified', 'use': 'reference_only',
                'usage_basis': 'Публичные материалы официального суда; сайт разрешает воспроизведение со ссылкой на источник.',
                'review_status': 'requires_current_law_and_field_mapping_review'}
        except Exception as error:
            print('FORM_FAILED', type(error).__name__, url, flush=True); return None
    entries = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        for row in pool.map(download, list(files.values())[:90]):
            if row: entries[row['id']] = row
    previous = ROOT / 'manifest.json'
    if previous.exists():
        for row in json.loads(previous.read_text(encoding='utf-8')):
            entries.setdefault(row['id'], row)
    rows = sorted(entries.values(), key=lambda row: row['id'])
    previous.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'downloaded': len(rows), 'searchable_text': sum(row['characters'] >= 200 for row in rows)}, ensure_ascii=False), flush=True)


if __name__ == '__main__': main()
