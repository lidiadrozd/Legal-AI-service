"""Collect provenance for actual source forms. No authenticated access or scraping bypass."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.parse import urljoin
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
import importlib.util
_spec = importlib.util.spec_from_file_location("document_scenarios", ROOT / "backend/app/services/document_scenarios.py")
_module = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)
SCENARIOS = _module.SCENARIOS

OUTPUT = ROOT / "artifacts" / "document_templates_2026-10-24"
CHECKED = "2026-10-24"


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.current = None
        self.title = []
        self.in_title = False
        self.text = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"script", "style"}: self.skip += 1
        if tag == "title": self.in_title = True
        if tag == "a": self.current = [attrs.get("href", ""), []]

    def handle_endtag(self, tag):
        if tag in {"script", "style"}: self.skip = max(0, self.skip - 1)
        if tag == "title": self.in_title = False
        if tag == "a" and self.current:
            self.links.append((self.current[0], " ".join(self.current[1])))
            self.current = None

    def handle_data(self, data):
        value = " ".join(data.split())
        if not value or self.skip: return
        self.text.append(value)
        if self.in_title: self.title.append(value)
        if self.current: self.current[1].append(value)


def fetch(url):
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; LegalFormsResearch/1.0)"})
    with urlopen(request, timeout=35) as response:
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
        parser = Page()
        parser.feed(raw.decode(charset, errors="replace"))
        return parser, raw, response.geturl(), response.headers.get("Content-Type", "")


MATCHES = {
    "pretense_debt_loan": "Претензия о возврате денежных средств по договору займа (между физическими лицами)",
    "pretense_debt_rent": "Претензия о взыскании задолженности по договору аренды (между физическими лицами)",
    "pretense_debt_services": None,
    "pretense_debt_supply": None,
    "claim_debt_loan": "Исковое заявление о взыскании задолженности и процентов за пользование чужими денежными средствами (неустойки) по договору займа",
    "claim_debt_rent": "Исковое заявление о взыскании задолженности по договору аренды",
    "claim_debt_services": "Исковое заявление о взыскании задолженности по договору возмездного оказания услуг",
    "claim_debt_supply": "Исковое заявление о взыскании задолженности и неустойки по договору поставки",
    "pretense_consumer_defective_goods": "Претензия о возврате денежных средств, уплаченных за товар ненадлежащего качества (не технически сложный товар)",
    "pretense_consumer_late_delivery": "Претензия о нарушении срока доставки товара, приобретенного дистанционным способом (возврат уплаченной суммы)",
    "pretense_consumer_defective_service": None,
    "pretense_damage_flood": "Претензия о возмещении ущерба, причиненного заливом квартиры (физические лица)",
    "pretense_damage_property": "Претензия о возмещении ущерба, причиненного имуществу (между физическими лицами)",
    "claim_damage_flood": "Исковое заявление о взыскании ущерба, причиненного заливом квартиры",
    "claim_damage_property": None,
    "claim_consumer": "Исковое заявление о защите прав потребителей, связанных с продажей некачественного товара",
    "contract_services": "Абонентский договор возмездного оказания услуг/Договор возмездного оказания услуг",
    "contract_work": "Договор подряда",
    "contract_housing": "Договор найма жилого помещения",
    "contract_loan": "Договор займа",
    "act_services": None,
    "act_work": "Акт приема-передачи выполненных работ по договору подряда",
    "act_loan_receipt": "Расписка заемщика",
    "power_of_attorney": "Доверенность",
}

EXTRA = {
    "appeal_civil": "https://base.garant.ru/55724440/",
    "motion_costs": "https://base.garant.ru/1969855/",
    "appeal_arbitration": "https://base.garant.ru/1970521/",
    "act_services": "https://base.garant.ru/55741182/",
    "motion_attach": "https://nnoblsud.ru/docs/forms/Obrazci-inih-dokumentov%2C-otnosyashhihsya-k-rassmotreniyu-grazhdanskih-del/priobsh-doc-k-isk-gr-pr.pdf",
    "motion_postpone": "https://www.advokatomsk.su/obrazcy_dokumentov/",
    "motion_objection": "https://vologodsky--vld.sudrf.ru/modules.php?name=information&rid=19",
    "complaint_labor_agency": "https://www.garant.ru/consult/practice/1813520/",
    "complaint_consumer_agency": "https://petition.rospotrebnadzor.ru/petition/",
    "pretense_consumer_defective_service": "https://32.rospotrebnadzor.ru/index.php?Itemid=113&catid=12&id=47%3Aobraztsy-napisaniya-pretenzij&option=com_content&view=article",
}


def collect():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    catalog, _, _, _ = fetch("https://kpd.garant.ru/")
    all_links = [(urljoin("https://kpd.garant.ru/", href), label) for href, label in catalog.links]
    (OUTPUT / "garant_catalog_links.json").write_text(json.dumps(all_links, ensure_ascii=False, indent=2), encoding="utf-8")
    jobs = []
    for key, scenario in SCENARIOS.items():
        target = MATCHES.get(key)
        matches = [(url, title) for url, title in all_links if target and title == target]
        if matches: jobs.append((key, *matches[0]))
        elif key in EXTRA: jobs.append((key, EXTRA[key], scenario.title))
        else: jobs.append((key, None, scenario.title))

    def inspect(job):
        key, url, title = job
        item = {"scenario": key, "scenario_title": SCENARIOS[key].title, "url": url,
                "source_title": title, "checked_at": CHECKED, "access": "not_selected",
                "source_revision": None, "legal_review": "not_performed", "usage_rights": "not_confirmed"}
        if not url: return item
        try:
            page, raw, final, content_type = fetch(url)
            text = " ".join(page.text)
            item.update(source_title=" ".join(page.title) or title, url=final,
                        content_sha256=sha256(raw).hexdigest(), content_type=content_type,
                        access="public_html", bytes=len(raw))
            dates = re.findall(r"(?:январ[ья]|феврал[ья]|март[а]?|апрел[ья]|ма[йя]|июн[ья]|июл[ья]|август[а]?|сентябр[ья]|октябр[ья]|ноябр[ья]|декабр[ья])\s+202[0-9]", item["source_title"], re.I)
            item["source_revision"] = dates[0] if dates else None
            item["export_requires_account"] = "Шаг 1. Купите документ" in text or "Войти" in text
            # Store only factual section headings and metadata, not copyrighted full forms.
            item["public_body_present"] = (len(text) > 3500 and "Текст документа отсутствует в свободном доступе" not in text
                                           and "Актуальная версия заинтересовавшего Вас документа доступна только" not in text)
            item["source_kind"] = "source_form" if any(x in url for x in ["kpd.garant.ru", "base.garant.ru", ".pdf"]) else "reference_or_form_collection"
        except Exception as exc:
            item.update(access="unavailable", error=type(exc).__name__)
        return item

    with ThreadPoolExecutor(max_workers=6) as pool:
        records = list(pool.map(inspect, jobs))
    (OUTPUT / "sources.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    for record in records:
        print(record["scenario"], record["access"], record.get("source_revision") or "revision not stated")
    return records


if __name__ == "__main__": collect()
