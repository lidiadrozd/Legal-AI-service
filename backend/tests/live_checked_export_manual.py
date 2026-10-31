"""Export the actually prepared synthetic GigaChat state through the HTTP API."""
import asyncio
from io import BytesIO
import json
from pathlib import Path
import secrets

import httpx
from docx import Document as WordDocument
from sqlalchemy import select, delete
from app.core.security import create_access_token, get_password_hash
from app.db.session import AsyncSessionLocal
from app.models.user import User
from app.models.chat import ChatSession
from app.models.document import Document
from app.services.document_workflow import pending_fields


async def main():
    state = json.loads(Path("/app/tests/live_document_edited_state.json").read_text(encoding="utf-8"))
    state["phase"] = "ready"
    assert not pending_fields(state)
    email = "checked-export-" + secrets.token_hex(6) + "@example.com"
    async with AsyncSessionLocal() as db:
        user = User(email=email, full_name="Synthetic editorial test", hashed_password=get_password_hash(secrets.token_hex(24)),
                    is_active=True, consent_given=True)
        db.add(user)
        await db.flush()
        user_id = user.id
        chat = ChatSession(user_id=user_id, title="Checked editorial export", document_workflow=state)
        db.add(chat)
        await db.flush()
        cid = chat.id
        await db.commit()
    try:
        async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", trust_env=False, timeout=300,
                headers={"Authorization": "Bearer " + create_access_token({"sub": email})}) as client:
            response = await client.post(f"/documents/interviews/{cid}/export")
            response.raise_for_status()
            download = await client.get(f"/documents/{response.json()['document_id']}/download")
            download.raise_for_status()
            text = "\n".join(p.text for p in WordDocument(BytesIO(download.content)).paragraphs)
            assert "Во время зарядки телефона" in text
            assert "угрозу причинения вреда здоровью" in text
            assert "я заряжала" not in text and "сам посчитай" not in text and "поясни вопрос" not in text
            Path("/app/tests/live_conversation_export.docx").write_bytes(download.content)
            print(json.dumps({"status": "SUCCESS", "http_export": response.status_code,
                "http_download": download.status_code, "bytes": len(download.content), "original_facts_retained": True}), flush=True)
    finally:
        async with AsyncSessionLocal() as db:
            paths = (await db.execute(select(Document.file_path).where(Document.user_id == user_id))).scalars().all()
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()
            for path in paths:
                if path: Path(path).unlink(missing_ok=True)


asyncio.run(main())
