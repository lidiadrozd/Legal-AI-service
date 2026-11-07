"""Operator-authored summaries, explicitly distinguished from statutory quotations."""
from pathlib import Path
import hashlib
import json

root = Path(__file__).resolve().parents[1] / "backend/rag_docs"
entries = [
    ("tk_rf_article_80_summary.txt", "80", "1", "", "https://base.garant.ru/12125268/134df926347d321d8dc82c9551519f33/",
     "ТК РФ, статья 80, часть 1. Увольнение по инициативе работника (по собственному желанию).\n\n"
     "Краткое изложение, не дословный текст закона: инициатором здесь выступает работник, который письменно уведомляет работодателя. "
     "Общий срок предупреждения составляет две недели; закон может устанавливать иной срок. Его отсчёт начинается на следующий день после получения заявления работодателем. "
     "Пояснение об области применения: отсутствие заявления препятствует увольнению по собственному желанию. "
     "Это не означает, что заявление требуется при любом другом основании прекращения трудового договора. "
     "Увольнение по инициативе работодателя регулируется отдельно, в частности статьёй 81 ТК РФ.\n"),
    ("tk_rf_article_81_point_5_summary.txt", "81", "1", "5", "https://www.consultant.ru/document/cons_doc_LAW_34683/6a7ba42d8fda3a1ba186a9eb5c806921998ae7d1/",
     "ТК РФ, статья 81, часть 1, пункт 5. Увольнение по инициативе работодателя.\n\n"
     "Краткое изложение, не дословный текст закона: одним из оснований выступает повторное нарушение работником своих трудовых обязанностей без уважительных причин при наличии дисциплинарного взыскания. "
     "Пояснение: неоднократные опоздания требуют проверки именно условий этого основания и процедуры взыскания; "
     "они не превращают увольнение работодателем в увольнение по собственному желанию по статье 80 ТК РФ. "
     "По одному сообщению об опозданиях нельзя признать увольнение законным: необходимо проверить факты, взыскание и соблюдение установленной процедуры.\n"),
]
manifest_path = root / "legal_sources.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
manifest["notice"] = "Небольшая база проверенных фрагментов и явно помеченных авторских изложений. Не является полной базой законодательства или юридическим заключением."
for name, article, part, point, url, content in entries:
    raw = content.encode("utf-8")
    (root / name).write_bytes(raw)
    manifest["sources"] = [s for s in manifest["sources"] if s["file"] != name]
    manifest["sources"].append({"file": name, "document_key": "ru:197-fz:2001-12-30", "article": article,
        "part": part, "point": point, "source_url": url, "revision": "2026-05-25", "checked_at": "2026-10-24",
        "content_kind": "operator_summary", "sha256": hashlib.sha256(raw).hexdigest()})
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("Added 2 sourced summaries: TK 80 and TK 81(1)(5)")
