"""Opt-in live check in an isolated PostgreSQL schema and Redis namespace.
Run in the API container with --live-model --evidence <verified report> --report <path>.
Never prints credentials, JWTs or model answer text. Deletes its own schema afterward.
"""
import argparse
import asyncio
import contextlib
import io
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.api import chat, notifications
from app.core.config import settings
from app.core.security import create_access_token
from app.db.base_class import Base
from app.db.session import engine, get_db
from app.models.user import User
from app.models.chat_law_reference import ChatLawReference
from app.services import notification_bus
from app.services.law_change_parser import ParsedLawChange
from app.services.law_change_monitor import persist_parsed_changes
from app.services.law_notification_service import dispatch_law_change_notifications
from app.services.legal_sources import NormIdentity, load_legal_source_catalog


async def verify(evidence_path, *, without_rag=False):
    evidence = json.loads(Path(evidence_path).read_text(encoding="utf-8"))["mapped_norms"][0]
    norm = NormIdentity.from_dict(evidence["norm"])
    if without_rag:
        settings.RAG_ENABLED = False
    else:
        assert norm in {s.norm for s in load_legal_source_catalog(Path(settings.RAG_DOCS_PATH)).values()}
    assert evidence["evidence"]["method"] == "consultant_explicit_link"
    nonce = uuid4().hex
    schema = "notification_check_" + nonce
    notification_bus.NOTIFICATION_CHANNEL_PREFIX = "verification:" + nonce
    notification_bus.NOTIFICATION_BROADCAST_CHANNEL = "verification:" + nonce + ":broadcast"
    settings.CHAT_RESPONSE_CACHE_ENABLED = False
    stage = "schema_setup"
    report = {"isolation": "temporary_postgresql_schema_and_redis_namespace", "live_model": True, "rag_enabled": not without_rag, "change_source": "previously_verified_snapshot"}
    async with engine.connect() as conn:
        created = False
        try:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            created = True
            await conn.execute(text(f'SET search_path TO "{schema}"'))
            await conn.run_sync(Base.metadata.create_all)
            await conn.commit()
            async with AsyncSession(bind=conn, expire_on_commit=False) as db:
                stage = "seed_users"
                user = User(email=nonce + "@example.invalid", full_name="Контрольный пользователь", hashed_password="!", is_active=True, consent_given=True)
                other = User(email="other-" + nonce + "@example.invalid", full_name="Другой контрольный пользователь", hashed_password="!", is_active=True)
                db.add_all([user, other])
                await db.commit()
                app = FastAPI()
                app.include_router(chat.router)
                app.include_router(notifications.router)
                async def isolated_db():
                    yield db
                app.dependency_overrides[get_db] = isolated_db
                headers = {"Authorization": "Bearer " + create_access_token({"sub": user.email})}
                other_headers = {"Authorization": "Bearer " + create_access_token({"sub": other.email})}
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://verification", headers=headers) as client:
                    stage = "create_chat"
                    response = await client.post("/chat/new")
                    assert response.status_code == 200, "Chat creation failed"
                    chat_id = response.json()["id"]
                    stage = "live_chat_answer"
                    response = await asyncio.wait_for(client.post(f"/chat/{chat_id}/send_stream", json={"content": "Я платежный агент в России. Какие операции могут осуществляться по специальному банковскому счету платежного агента? Ответьте по части 16 статьи 4 Федерального закона от 03.06.2009 № 103-ФЗ и укажите полные реквизиты нормы рядом с утверждением."}), timeout=90)
                    assert response.status_code == 200 and "[DONE]" in response.text
                    stage = "saved_reference"
                    refs = list(await db.scalars(select(ChatLawReference)))
                    if not any(NormIdentity(r.document_key, r.article, r.part, r.point) == norm for r in refs):
                        from app.models.chat import Message
                        from app.models.llm_usage import LlmUsageEvent
                        from app.services.rag_context import build_rag_bundle
                        from sqlalchemy import func
                        answers = list(await db.scalars(select(Message).where(Message.role == "assistant")))
                        diagnostics = {"reference_count": len(refs), "assistant_saved": bool(answers), "citation_marker_present": any("[Источник " in a.content for a in answers), "model_usage_recorded": bool(await db.scalar(select(func.count()).select_from(LlmUsageEvent)))}
                        for flag in ("GigaChat HTTP", "Ошибка получения OAuth", "Не удалось подключиться", "Timeout", "ForeignKeyViolation", "UniqueViolation", "NotNullViolation", "UndefinedTable", "collation", "Unicode", "AttributeError"):
                            diagnostics[flag] = any(flag in a.content for a in answers)
                        import re
                        diagnostics["model_http_statuses"] = sorted({int(code) for a in answers for code in re.findall(r"GigaChat HTTP (\d{3})", a.content)})
                        error = AssertionError("No matching cited reference")
                        error.safe_diagnostics = diagnostics
                        raise error
                    report["saved_references"] = len(refs)
                    change = ParsedLawChange(title="О деятельности по приему платежей физических лиц, осуществляемой платежными агентами", change_date=datetime(2026,7,26,tzinfo=timezone.utc), description=evidence["evidence"]["instruction"], source_url=evidence["evidence"]["publication_url"], document_number="103-ФЗ", affected_norms=(norm,), norm_evidence=(evidence["evidence"],))
                    stage = "import_change"
                    imported = await persist_parsed_changes(db, [change])
                    assert len(imported) == 1
                    redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
                    pubsub = redis.pubsub()
                    try:
                        await pubsub.subscribe(notification_bus.build_user_channel(user.id))
                        await pubsub.get_message(timeout=2)
                        stage = "dispatch_first"
                        first = await dispatch_law_change_notifications(db)
                        assert first == 1
                        stage = "redis_event"
                        event = await pubsub.get_message(ignore_subscribe_messages=True, timeout=3)
                        assert event and event["type"] == "message", "Redis event missing"
                        payload = json.loads(event["data"])
                        assert payload["meta"]["chat_id"] == chat_id
                        report["redis_event_received"] = True
                        stage = "dispatch_repeat"
                        second = await dispatch_law_change_notifications(db)
                        assert second == 0
                        assert not await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
                    finally:
                        await pubsub.aclose()
                        await redis.aclose()
                    stage = "rest_notification"
                    response = await client.get("/notifications")
                    assert response.status_code == 200
                    rows = response.json()
                    assert len(rows) == 1 and rows[0]["meta"]["chat_id"] == chat_id
                    report["notifications_created"] = first
                    report["repeat_notifications_created"] = second
                    report["notification_basis"] = rows[0]["meta"]["notification_basis"]
                    stage = "linked_chat"
                    response = await client.get(f"/chat/{chat_id}/history")
                    assert response.status_code == 200 and len(response.json()) >= 2
                    report["linked_chat_accessible"] = True
                    stage = "ownership_check"
                    response = await client.get("/notifications", headers=other_headers)
                    assert response.status_code == 200 and response.json() == []
                    assert (await client.get(f"/chat/{chat_id}/history", headers=other_headers)).status_code == 404
                    report["other_user_isolated"] = True
                    stage = "mark_read"
                    assert (await client.patch(f"/notifications/{rows[0]['id']}/read")).json()["is_read"] is True
                    report["mark_read_verified"] = True
        except Exception as exc:
            exc.verification_stage = stage
            raise
        finally:
            await conn.rollback()
            if created:
                await conn.execute(text('SET search_path TO public'))
                await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
                await conn.commit()
                report["temporary_schema_deleted"] = True
    await engine.dispose()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-model", action="store_true", required=True)
    parser.add_argument("--without-rag", action="store_true")
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            report = asyncio.run(verify(args.evidence, without_rag=args.without_rag))
        report["state"] = "ok"
    except Exception as exc:
        report = {"state": "error", "error_type": type(exc).__name__, "stage": getattr(exc, "verification_stage", "unknown"), "diagnostics": getattr(exc, "safe_diagnostics", {})}
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    raise SystemExit(0 if report["state"] == "ok" else 1)
