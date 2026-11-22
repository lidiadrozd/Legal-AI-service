from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.prompts import DOCUMENT_JSON_EXAMPLE
from app.models.chat import ChatSession, Message
from app.services import document_ai_generator


@pytest.mark.asyncio
async def test_generation_passes_recent_current_chat_turns_to_llm(
    client, db_session, monkeypatch, tmp_path,
):
    monkeypatch.setattr("app.core.config.settings.DOCUMENTS_STORAGE_DIR", str(tmp_path))
    chat = ChatSession(user_id=1, title="Current")
    other = ChatSession(user_id=1, title="Other")
    db_session.add_all([chat, other])
    await db_session.flush()
    turns = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"Факт {i}"}
        for i in range(24)
    ]
    db_session.add_all([Message(chat_id=chat.id, **turn) for turn in turns])
    db_session.add(Message(chat_id=other.id, role="user", content="Другой чат"))
    await db_session.commit()
    llm = SimpleNamespace(chat_completion=AsyncMock(side_effect=[
        SimpleNamespace(content="invalid JSON"),
        SimpleNamespace(content=DOCUMENT_JSON_EXAMPLE),
    ]))
    monkeypatch.setattr(document_ai_generator, "get_gigachat_client", AsyncMock(return_value=llm))

    response = await client.post("/documents/generate-ai", json={
        "prompt": "Составь претензию по нашей переписке", "chat_id": chat.id,
        "filename": "claim", "output_format": "txt",
    })

    assert response.status_code == 201, response.text
    messages = llm.chat_completion.call_args_list[0].args[0]
    assert messages[0]["role"] == "system"
    assert messages[1:-1] == turns[-20:]
    assert "Составь претензию по нашей переписке" in messages[-1]["content"]
    assert llm.chat_completion.call_args_list[1].args[0][:-2] == messages


@pytest.mark.asyncio
@pytest.mark.parametrize("owner", [2, None])
async def test_generation_rejects_unavailable_chat(client, db_session, monkeypatch, owner):
    chat = ChatSession(user_id=owner, title="Unavailable")
    db_session.add(chat)
    await db_session.commit()
    provider = AsyncMock()
    monkeypatch.setattr(document_ai_generator, "get_gigachat_client", provider)
    response = await client.post("/documents/generate-ai", json={
        "prompt": "Составь претензию по нашей переписке", "chat_id": chat.id,
        "filename": "claim",
    })
    assert response.status_code == 404
    provider.assert_not_awaited()


@pytest.mark.asyncio
async def test_generation_bounds_history_and_keeps_latest_facts(monkeypatch):
    llm = SimpleNamespace(chat_completion=AsyncMock(
        return_value=SimpleNamespace(content=DOCUMENT_JSON_EXAMPLE),
    ))
    monkeypatch.setattr(document_ai_generator, "get_gigachat_client", AsyncMock(return_value=llm))
    await document_ai_generator.generate_ai_document_text(
        "Составь претензию по нашей переписке",
        chat_history=[
            {"role": "user", "content": "старое"},
            {"role": "assistant", "content": "а" * 13000},
            {"role": "user", "content": "Сумма 100 рублей"},
        ],
    )
    history = llm.chat_completion.call_args.args[0][1:-1]
    assert sum(len(turn["content"]) for turn in history) == 12000
    assert history[-1] == {"role": "user", "content": "Сумма 100 рублей"}
