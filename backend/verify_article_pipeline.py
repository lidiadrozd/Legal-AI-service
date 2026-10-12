"""Verify article detection in a disposable PostgreSQL schema using synthetic HTTP."""
import asyncio
import json
import logging
from pathlib import Path
from uuid import uuid4
import httpx
from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession
from app import models
from app.db.base_class import Base
from app.db.session import engine
from app.models.user import User
from app.models.chat import ChatSession, Message
from app.models.notification import Notification
from app.services.answer_norms import extract_answer_norms, TK_KEY
from app.services.law_reference_service import save_chat_law_references
from app.services.law_change_monitor import refresh_tracked_article_snapshots
from app.services import law_notification_service as dispatcher

async def verify():
    schema = "article_check_" + uuid4().hex
    report = {"synthetic_http": True, "real_postgresql": True}
    dispatcher.publish_notification = lambda *args, **kwargs: None
    async with engine.connect() as connection:
        await connection.execute(text('CREATE SCHEMA "'+schema+'"'))
        try:
            await connection.execute(text('SET search_path TO "'+schema+'"'))
            await connection.run_sync(Base.metadata.create_all)
            await connection.commit()
            async with AsyncSession(bind=connection, expire_on_commit=False) as db:
                user = User(email=uuid4().hex+"@example.invalid", full_name="Контрольный клиент", hashed_password="!", is_active=True)
                other = User(email=uuid4().hex+"@example.invalid", full_name="Контрольный клиент", hashed_password="!", is_active=True)
                db.add_all([user, other]); await db.flush()
                chat = ChatSession(user_id=user.id, title="Контрольная статья")
                db.add(chat); await db.flush()
                question = Message(chat_id=chat.id, role="user", content="Контрольный вопрос")
                answer = Message(chat_id=chat.id, role="assistant", content="Основание: статья 80 ТК РФ.")
                db.add_all([question, answer]); await db.flush()
                count = await save_chat_law_references(db, user_id=user.id, chat_id=chat.id,
                    user_message_id=question.id, assistant_message_id=answer.id,
                    references=extract_answer_norms(answer.content))
                assert count == 1
                await db.commit()
                content = {"value":"Первый текст."}
                def handler(request):
                    return httpx.Response(200, text='<div class="document-page__content"><p>Трудовой кодекс Российской Федерации от 30.12.2001 N 197-ФЗ (ред. от 01.10.2026)</p><p>Статья 80. Увольнение</p><p>'+content["value"]+'</p></div>')
                tracked = [("https://www.consultant.ru/document/cons_doc_LAW_34683/", TK_KEY)]
                async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                    assert await refresh_tracked_article_snapshots(db, client, tracked) == []
                    assert await dispatcher.dispatch_law_change_notifications(db) == 0
                    report["baseline_notifications"] = 0
                    content["value"] = "Другой текст."
                    changes = await refresh_tracked_article_snapshots(db, client, tracked)
                    assert len(changes) == 1
                    assert "Первый текст." in changes[0].old_version
                    assert "Другой текст." in changes[0].new_version
                    assert await dispatcher.dispatch_law_change_notifications(db) == 1
                    assert await refresh_tracked_article_snapshots(db, client, tracked) == []
                    assert await dispatcher.dispatch_law_change_notifications(db) == 0
                    assert await db.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == other.id)) == 0
                    report.update(saved_reference=True, changed_article="80", notifications_created=1,
                        repeated_notifications=0, other_user_isolated=True, source_texts_saved=True)
        finally:
            await connection.rollback()
            await connection.execute(text('SET search_path TO public'))
            await connection.execute(text('DROP SCHEMA "'+schema+'" CASCADE'))
            await connection.commit()
            report["temporary_schema_deleted"] = True
    await engine.dispose()
    report["state"] = "ok"
    return report

if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    try:
        report = asyncio.run(verify())
    except Exception as exc:
        report = {"state":"error", "error_type":type(exc).__name__}
    Path("/tmp/article_pipeline_check.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    raise SystemExit(0 if report["state"] == "ok" else 1)
