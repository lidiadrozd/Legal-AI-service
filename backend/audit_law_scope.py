"""Audit public overview entries; optionally mark unconfirmed scopes, never delete data."""
import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import select
from app.db.session import AsyncSessionLocal, engine
from app.models.law_changes import LawChange

async def main(apply, report_path):
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "applied": apply, "entries": []}
    async with AsyncSessionLocal() as db:
        rows = list(await db.scalars(select(LawChange).where(LawChange.source_url.like("https://www.consultant.ru/%"))))
        for row in rows:
            evidence = (row.diff or {}).get("norm_evidence", [])
            if not evidence or not all(e.get("method") == "overview_document_identity" for e in evidence):
                continue
            info = (row.diff or {}).get("norm_resolution", {})
            reason = "amendment_link_missing" if not info.get("amendment_source_urls") else "amendment_unresolved"
            resolution = {"status": "unresolved", "reason": reason, "event_kind": "edition_listing"}
            report["entries"].append({"change_id": row.id, "document_key": evidence[0].get("document_key"),
                "source_url": row.source_url, "revision_date": row.change_date.isoformat() if row.change_date else None,
                "is_amending_act": row.change_title.casefold().startswith("о внесении изменений"),
                **resolution})
            if apply:
                row.diff = {**(row.diff or {}), "scope_resolution": resolution}
        if apply:
            await db.commit()
    report["unconfirmed_entries"] = len(report["entries"])
    report["amending_act_entries"] = sum(e["is_amending_act"] for e in report["entries"])
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k != "entries"}))
    await engine.dispose()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    asyncio.run(main(args.apply, args.report))
