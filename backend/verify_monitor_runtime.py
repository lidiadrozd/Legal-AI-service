"""Read-only runtime report without user content, credentials or source excerpts."""
import asyncio
import json
import sys
from pathlib import Path
from sqlalchemy import select, func
from app.db.session import AsyncSessionLocal, engine
from app.models.law_monitor_state import LawMonitorState
from app.models.law_changes import LawChange
from app.models.chat_law_reference import LawChangeNorm
from app.celery_app import celery_app

async def main():
    async with AsyncSessionLocal() as db:
        states = list(await db.scalars(select(LawMonitorState)))
        norms = (await db.execute(select(LawChangeNorm.document_key, LawChangeNorm.article,
            LawChangeNorm.part).limit(5))).all()
        report = {
            "daily_hour_yekaterinburg": 11,
            "retry_hours_yekaterinburg": [12, 14, 17],
            "task_state": celery_app.AsyncResult(sys.argv[1]).state if len(sys.argv) > 1 else None,
            "sources": [{
                "last_attempt_at": s.last_attempt_at.isoformat() if s.last_attempt_at else None,
                "last_success_at": s.last_success_at.isoformat() if s.last_success_at else None,
                "last_error": s.last_error,
                "coverage_gap": s.coverage_gap,
                "completed_periods": len((s.progress or {}).get("completed_periods", [])),
                "pending_periods": len((s.progress or {}).get("pending_periods", {})),
            } for s in states],
            "law_changes_total": await db.scalar(select(func.count()).select_from(LawChange)),
            "norm_mappings_total": await db.scalar(select(func.count()).select_from(LawChangeNorm)),
            "norm_examples": [{"document_key": n.document_key, "article": n.article, "part": n.part} for n in norms],
        }
        Path("/tmp/monitor_retry_runtime.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
