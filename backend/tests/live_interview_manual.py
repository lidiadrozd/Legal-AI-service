"""Opt-in local integration probe. Creates and removes only its own test user."""
import asyncio
from io import BytesIO
import json
from pathlib import Path
import secrets
import re

import httpx
from docx import Document as WordDocument
from sqlalchemy import delete, select
from app.core.security import create_access_token, get_password_hash
from app.db.session import AsyncSessionLocal
from app.models.user import User
from app.models.document import Document


async def main():
    email = f"interview-probe-{secrets.token_hex(6)}@example.com"
    async with AsyncSessionLocal() as db:
        user = User(email=email, full_name="Тест исправлений", hashed_password=get_password_hash(secrets.token_hex(24)),
                    is_active=True, consent_given=True)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_id = user.id
    report = []
    try:
        async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", trust_env=False, timeout=300,
                                    headers={"Authorization": "Bearer " + create_access_token({"sub": email})}) as client:
            response = await client.post("/documents/interviews", json={
                "prompt": "Нужна претензия: знакомый не вернул 7 тысяч рублей по расписке", "output_format": "docx"})
            response.raise_for_status()
            cid = response.json()["chat_id"]
            answers = {"sender": "Вавилов Андрей Андреевич", "sender_address": "г. Екатеринбург, ул. Блюхера, д. 50, кв. 5",
                       "recipient": "михайлова варвара максимовна", "recipient_address": "не знаю",
                       "agreement": "Расписка от 01.03.2026", "due_date": "15.03.2026",
                       "transfer": "Передал наличными 01.03.2026 Михайловой Варваре Максимовне, есть расписка",
                       "amount": "7 тыс руб", "requests": "Вернуть основной долг 7000 рублей",
                       "response_term": "не знаю", "attachments": "Копия расписки от 01.03.2026",
                       "date": "24.10.2026", "signature": "Вавилов Андрей Андреевич",
                       "facts": "Знакомая не вернула 7000 рублей по расписке, срок возврата истёк 15.03.2026"}
            seen = {}
            file_id = None
            for step in range(25):
                state_response = await client.get(f"/documents/interviews/{cid}")
                state_response.raise_for_status()
                state = state_response.json()
                report.append({"step": step, "phase": state["phase"], "questions": state.get("last_questions"),
                               "fields": {k: v.get("status") for k, v in state.get("fields", {}).items()}})
                print(json.dumps(report[-1], ensure_ascii=False), flush=True)
                if state["phase"] == "ready": break
                keys = state.get("last_questions", [])
                assert len(keys) == 1, state
                key = keys[0]
                seen[key] = seen.get(key, 0) + 1
                assert seen[key] <= 2, f"Repeated field: {key}"
                response = await client.post(f"/chat/{cid}/send_stream", json={"content": answers.get(key, "не знаю")})
                response.raise_for_status()
                chunks = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: {")]
                answer_text = "".join(chunk.get("content", "") for chunk in chunks)
                print("reply: " + answer_text[:1200], flush=True)
                assert "Ошибка GigaChat" not in answer_text, answer_text
                link = re.search(r"\]\(/documents/([0-9a-f-]{36})/download\)", answer_text)
                if link:
                    file_id = link[1]
            assert state["phase"] == "ready"
            assert state["fields"]["amount"]["value"] == "7000.00"
            assert state["fields"]["recipient"]["status"] == "filled"
            assert file_id, "The final chat reply must contain an actual downloadable file"
            assert state["generated_document"]["document_id"] == file_id
            assert "Вавилов" not in answer_text, "Do not dump the document body into the chat"
            response = await client.post(f"/documents/interviews/{cid}/export")
            response.raise_for_status()
            assert response.json()["document_id"] == file_id, "Repeat export must reuse the prepared file"
            response = await client.post(f"/chat/{cid}/send_stream", json={"content": "А где файл?"})
            response.raise_for_status()
            chunks = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: {")]
            repeated = ''.join(chunk.get('content', '') for chunk in chunks)
            assert f'/documents/{file_id}/download' in repeated
            download = await client.get(f"/documents/{file_id}/download")
            download.raise_for_status()
            text = "\n".join(p.text for p in WordDocument(BytesIO(download.content)).paragraphs)
            assert "7000 рублей" in text and "Вавилов" in text and "{{" not in text
            out = Path("/app/tests/live_interview_result.docx")
            out.write_bytes(download.content)
            Path("/app/tests/live_interview_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print("SUCCESS: actual HTTP interview -> GigaChat -> DOCX; turns=" + str(len(report)), flush=True)
    finally:
        async with AsyncSessionLocal() as db:
            paths = (await db.execute(select(Document.file_path).where(Document.user_id == user_id))).scalars().all()
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()
            for path in paths:
                if path: Path(path).unlink(missing_ok=True)


if __name__ == "__main__": asyncio.run(main())
