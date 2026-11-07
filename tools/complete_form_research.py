from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from urllib.request import urlopen, Request
from research_document_forms import OUTPUT, fetch


records = json.loads((OUTPUT / "sources.json").read_text(encoding="utf-8"))
by_key = {r["scenario"]: r for r in records}
for key, related in {"pretense_debt_services": "claim_debt_services", "pretense_debt_supply": "claim_debt_supply",
                     "claim_damage_property": "pretense_damage_property"}.items():
    record = by_key[key]
    parent = by_key[related]
    for prop in ("url", "source_title", "access", "content_sha256", "bytes", "public_body_present"):
        if prop in parent: record[prop] = parent[prop]
    record["source_kind"] = "related_form_not_exact_template"
    record["adaptation_note"] = "Самостоятельная редакция по нормативным требованиям с сопоставлением смежной реальной формы; точный исходный бланк не найден."

extra = {"contract_housing": ("https://base.garant.ru/1970644/", "октябрь 2026"),
         "contract_work": ("https://base.garant.ru/2060270/", "август 2026")}
for key, (url, revision) in extra.items():
    by_key[key]["additional_source"] = {"url": url, "revision_reported_by_publisher": revision,
        "verification": "title_seen_in_web_search; direct web viewer returned 403; not treated as a downloaded DOCX"}
for key in ("complaint_consumer_agency", "complaint_labor_agency", "motion_postpone", "motion_objection"):
    by_key[key]["source_kind"] = "reference_or_form_collection_not_exact_template"
    by_key[key]["adaptation_note"] = "Самостоятельная редакция; наличие точного современного исходного бланка не подтверждено."
by_key["act_services"]["adaptation_note"] = "Источник относится к услугам call-центра. Универсальная версия составлена самостоятельно; отраслевые условия не перенесены."
by_key["motion_attach"]["adaptation_note"] = "Источник о приобщении документов при устранении недостатков иска. Вариант приобщения доказательств по делу составлен отдельно."
(OUTPUT / "sources.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def download_original():
    directory = OUTPUT / "official_originals"
    directory.mkdir(exist_ok=True)
    originals = [("https://zpp.rospotrebnadzor.ru/Show/File/11908", "rospotrebnadzor_defective_goods.doc", "https://zpp.rospotrebnadzor.ru/handbook/torg/forms/50355"),
        ("https://nnoblsud.ru/docs/forms/Obrazci-inih-dokumentov%2C-otnosyashhihsya-k-rassmotreniyu-grazhdanskih-del/priobsh-doc-k-isk-gr-pr.pdf", "court_attach_documents.pdf", "https://nnoblsud.ru/")]
    result = []
    def one(item):
        url, name, source = item
        entry = {"url": url, "source_page": source, "filename": name, "source_revision": "not_stated", "checked_at": "2026-10-24"}
        try:
            with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as response:
                raw = response.read()
            expected = raw.startswith(b"%PDF") if name.endswith(".pdf") else raw.startswith(bytes.fromhex("d0cf11e0")) or raw.startswith(b"PK")
            if not expected: raise ValueError("The response is not the expected Office/PDF file")
            (directory / name).write_bytes(raw)
            entry.update(status="downloaded_original", bytes=len(raw), sha256=sha256(raw).hexdigest())
        except Exception as exc:
            entry.update(status="not_downloaded", error=type(exc).__name__)
        return entry
    with ThreadPoolExecutor(max_workers=2) as pool: result = list(pool.map(one, originals))
    (directory / "provenance.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__": download_original()
