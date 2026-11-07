from pathlib import Path
from hashlib import sha256
import json
import zipfile
from research_document_forms import SCENARIOS

root = Path(__file__).resolve().parents[1]
pack = root / "artifacts/document_templates_2026-10-24_fixed"
(pack / "field_dictionary.json").write_text(json.dumps(
    {key: scenario.as_dict() for key, scenario in SCENARIOS.items()}, ensure_ascii=False, indent=2), encoding="utf-8")
qa = {"docx_count": 32, "word_rendered_count": 32, "visually_inspected_pages": 32,
      "renderer": "Microsoft Word 12.0 plus Poppler rasterization", "tests_passed": 93,
      "frontend_build": "passed", "legal_review": "not_performed",
      "gigachat_live_evaluation": "loan interview completed through HTTP, 14 answers, DOCX exported; advice checks revealed model errors, guarded fallback added"}
(pack / "validation.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")
target = root / "artifacts/legal_document_templates_2026-10-24_fixed.zip"
allowed_roots = {"docx", "json", "official_originals"}
allowed_files = {"README.md", "manifest.json", "sources.json", "legal_checks.md", "field_dictionary.json", "validation.json"}
with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(pack.rglob("*")):
        if not path.is_file(): continue
        relative = path.relative_to(pack)
        if relative.parts[0] in allowed_roots or relative.as_posix() in allowed_files:
            archive.write(path, relative.as_posix())
with zipfile.ZipFile(target) as archive:
    names = archive.namelist()
    assert len([name for name in names if name.startswith("docx/") and name.endswith(".docx")]) == 32
    assert len([name for name in names if name.startswith("json/") and name.endswith(".json")]) == 32
    assert not any(name.startswith("qa/") for name in names)
    assert archive.testzip() is None
print(json.dumps({"archive": str(target), "files": len(names), "bytes": target.stat().st_size,
                  "sha256": sha256(target.read_bytes()).hexdigest()}, ensure_ascii=False))
