"""Opt-in synthetic questions through real GigaChat; isolated DB and Redis.
No real changes are announced. Removes only its own temporary schema.
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
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app import models
from app.api import chat, notifications
from app.core.config import settings
from app.core.security import create_access_token
from app.db.base_class import Base
from app.db.session import engine, get_db
from app.models.user import User
from app.models.chat import Message
from app.models.chat_law_reference import ChatLawReference
from app.services import notification_bus
from app.services.legal_sources import NormIdentity
from app.services.law_change_parser import ParsedLawChange
from app.services.law_change_monitor import persist_parsed_changes
from app.services.law_notification_service import dispatch_law_change_notifications

QUESTIONS = [
    ("dismissal", "Работаю по трудовому договору в России. Начальник требует завтра написать заявление по собственному желанию, хотя увольняться я не хочу. Нарушений с моей стороны нет. Как мне защитить себя?"),
    ("consumer", "Купила в магазине в России электрический чайник. Через три дня он перестал включаться. Чек есть, магазин предлагает только ремонт, а я хочу вернуть деньги. Что мне делать?"),
    ("rent", "Снимаю квартиру в России по письменному договору на год. Исправно плачу. Через два месяца собственник требует съехать за три дня, потому что решил сдать дороже. Договор не предусматривает такой причины. Какие у меня права?")]

FOLLOW_UPS = {
    "dismissal": "Уточняю: мне 30 лет, договор бессрочный, испытательного срока нет, дисциплинарных взысканий нет. Работодатель — ООО. Ничего не подписывала, требование прозвучало устно сегодня. Хочу продолжать работать. Как действовать сейчас?",
    "consumer": "Уточняю: покупка в обычном магазине, чек и гарантия на год есть. Чайник использовала по инструкции, повреждений нет. Продавцу вчера устно попросила вернуть деньги, письменную претензию пока не подавала. Хочу возврат денег. Какие действия предпринять?",
    "rent": "Уточняю: я и собственник — физические лица, это единственное жильё, договор подписан два месяца назад на год. Задолженности и нарушений нет. Требование было в сообщении вчера, суда не было. Договор разрешает досрочное расторжение только по соглашению или при нарушении условий. Хочу остаться до конца срока. Как действовать?"}

async def verify():
    nonce = uuid4().hex
    schema = "ordinary_check_" + nonce
    settings.RAG_ENABLED = False
    settings.CHAT_RESPONSE_CACHE_ENABLED = False
    notification_bus.NOTIFICATION_CHANNEL_PREFIX = "verification:" + nonce
    notification_bus.NOTIFICATION_BROADCAST_CHANNEL = "verification:" + nonce + ":broadcast"
    report = {"live_model": True, "rag_enabled": False, "changes": "synthetic", "cases": []}
    async with engine.connect() as conn:
        created = False
        try:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            created = True
            await conn.execute(text(f'SET search_path TO "{schema}"'))
            await conn.run_sync(Base.metadata.create_all)
            await conn.commit()
            async with AsyncSession(bind=conn, expire_on_commit=False) as db:
                users = [User(email=f"{i}-{nonce}@example.invalid", full_name="Тестовый пользователь", hashed_password="!", is_active=True, consent_given=True) for i in range(3)]
                db.add_all(users)
                await db.commit()
                app = FastAPI()
                app.include_router(chat.router)
                app.include_router(notifications.router)
                async def isolated_db():
                    yield db
                app.dependency_overrides[get_db] = isolated_db
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://verification") as client:
                    for user, (name, question) in zip(users, QUESTIONS):
                        headers = {"Authorization": "Bearer " + create_access_token({"sub": user.email})}
                        response = await client.post("/chat/new", headers=headers)
                        assert response.status_code == 200
                        chat_id = response.json()["id"]
                        response = await asyncio.wait_for(client.post(f"/chat/{chat_id}/send_stream", headers=headers, json={"content": question}), timeout=90)
                        assert response.status_code == 200 and "[DONE]" in response.text
                        answer = await db.scalar(select(Message.content).where(Message.chat_id == chat_id, Message.role == "assistant"))
                        refs = list(await db.scalars(select(ChatLawReference).where(ChatLawReference.chat_id == chat_id)))
                        turns = 1
                        if not any(r.article for r in refs):
                            response = await asyncio.wait_for(client.post(f"/chat/{chat_id}/send_stream", headers=headers, json={"content": FOLLOW_UPS[name]}), timeout=90)
                            assert response.status_code == 200 and "[DONE]" in response.text
                            turns = 2
                            answers = list(await db.scalars(select(Message.content).where(Message.chat_id == chat_id, Message.role == "assistant").order_by(Message.id)))
                            answer = "\n".join(answers)
                            refs = list(await db.scalars(select(ChatLawReference).where(ChatLawReference.chat_id == chat_id)))
                        case = {"turns": turns, "name": name, "saved_norms": [dict(document_key=r.document_key, article=r.article, part=r.part, point=r.point) for r in refs],
                                "citation_lines": [line for line in (answer or "").splitlines() if any(s in line.lower() for s in ("стать", "ст.", "закон", "кодекс", "тк рф", "гк рф"))]}
                        report["cases"].append(case)
                        # A precision check requires an actual saved article, not a whole-law fallback.
                        specific = next((r for r in refs if r.article), None)
                        if specific is None:
                            case["state"] = "missing_article_reference"
                            continue
                        exact = NormIdentity(specific.document_key, specific.article, specific.part, specific.point)
                        unmatched_article = NormIdentity(exact.document_key, "99999")
                        other_law = NormIdentity("test:unrelated-law", exact.article)
                        def change(label, norm):
                            return ParsedLawChange(title=f"ТЕСТ {name} {label}", change_date=datetime.now(timezone.utc), description="Синтетическая проверка уведомления, не настоящая поправка.", source_url=f"https://example.invalid/{name}/{label}", document_number=f"TEST-{name}-{label}", affected_norms=(norm,))
                        await persist_parsed_changes(db, [change("other_article", unmatched_article), change("other_law", other_law)])
                        unrelated_count = await dispatch_law_change_notifications(db)
                        case["unrelated_notifications_created"] = unrelated_count
                        # Whole-law references legitimately match any article. Record this explicitly.
                        case["has_whole_law_reference"] = any(not r.article and r.document_key == exact.document_key for r in refs)
                        await persist_parsed_changes(db, [change("matching", exact)])
                        case["matching_notifications_created"] = await dispatch_law_change_notifications(db)
                        case["repeat_notifications_created"] = await dispatch_law_change_notifications(db)
                        notes = (await client.get("/notifications", headers=headers)).json()
                        case["linked_chat_correct"] = all(n["meta"]["chat_id"] == chat_id for n in notes)
                        case["state"] = "ok" if case["matching_notifications_created"] == 1 and case["repeat_notifications_created"] == 0 and case["linked_chat_correct"] and unrelated_count == 0 else "needs_review"
                    for user, case in zip(users, report["cases"]):
                        headers = {"Authorization": "Bearer " + create_access_token({"sub": user.email})}
                        notes = (await client.get("/notifications", headers=headers)).json()
                        case["other_users_notifications_absent"] = all(f"ТЕСТ {case['name']} " in n["title"] for n in notes)
        finally:
            await conn.rollback()
            if created:
                await conn.execute(text('SET search_path TO public'))
                await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
                await conn.commit()
                report["temporary_schema_deleted"] = True
    await engine.dispose()
    report["state"] = "ok" if all(c["state"] == "ok" and c["other_users_notifications_absent"] for c in report["cases"]) else "needs_review"
    return report

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-model", action="store_true", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            report = asyncio.run(verify())
    except Exception as exc:
        report = {"state": "error", "error_type": type(exc).__name__}
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"state": report["state"], "cases": [{k:v for k,v in c.items() if k != "citation_lines"} for c in report.get("cases", [])]}, ensure_ascii=False))
    raise SystemExit(0 if report["state"] == "ok" else 1)
