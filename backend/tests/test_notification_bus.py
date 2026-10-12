
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import notification_bus


@pytest.mark.asyncio
async def test_stream_notifications_forwards_valid_message(monkeypatch):
    payload = {
        "title": "Изменение закона",
        "message": "Изменились правила уплаты взносов.",
        "severity": "medium",
        "type": "law_change",
        "id": 123,
    }

    pubsub = MagicMock()
    pubsub.subscribe = AsyncMock()
    pubsub.unsubscribe = AsyncMock()
    pubsub.aclose = AsyncMock()
    pubsub.get_message = AsyncMock(
        side_effect=[
            {
                "type": "message",
                "data": json.dumps(payload, ensure_ascii=False),
            },
        ]
    )

    client = MagicMock()
    client.pubsub.return_value = pubsub
    client.aclose = AsyncMock()

    monkeypatch.setattr(
        notification_bus.AsyncRedis,
        "from_url",
        MagicMock(return_value=client),
    )

    stop_event = asyncio.Event()
    received = []

    async def sender(message):
        received.append(message)
        stop_event.set()

    await notification_bus.stream_notifications(
        user_id=42,
        sender=sender,
        stop_event=stop_event,
    )

    assert received == [payload]
    pubsub.subscribe.assert_awaited_once_with(
        notification_bus.build_user_channel(42),
        notification_bus.NOTIFICATION_BROADCAST_CHANNEL,
    )
    pubsub.unsubscribe.assert_awaited_once()


@pytest.mark.asyncio
async def test_stream_notifications_skips_invalid_json(monkeypatch):
    pubsub = MagicMock()
    pubsub.subscribe = AsyncMock()
    pubsub.unsubscribe = AsyncMock()
    pubsub.aclose = AsyncMock()
    pubsub.get_message = AsyncMock(
        side_effect=[
            {"type": "message", "data": "not valid JSON"},
        ]
    )

    client = MagicMock()
    client.pubsub.return_value = pubsub
    client.aclose = AsyncMock()

    monkeypatch.setattr(
        notification_bus.AsyncRedis,
        "from_url",
        MagicMock(return_value=client),
    )

    stop_event = asyncio.Event()
    received = []

    async def sender(message):
        received.append(message)

    original_get_message = pubsub.get_message

    async def get_message_once(*args, **kwargs):
        result = await original_get_message(*args, **kwargs)
        stop_event.set()
        return result

    pubsub.get_message = AsyncMock(side_effect=get_message_once)

    await notification_bus.stream_notifications(
        user_id=42,
        sender=sender,
        stop_event=stop_event,
    )

    assert received == []
    pubsub.unsubscribe.assert_awaited_once()


def test_normalize_payload_uses_defaults():
    result = notification_bus._normalize_payload({})

    assert result["title"] == "Новое уведомление"
    assert result["message"] == ""
    assert result["severity"] == "medium"
    assert result["type"] == "system"
    assert result["timestamp"]


@pytest.mark.parametrize("severity", ["low", "medium", "high", "critical"])
def test_normalize_payload_accepts_valid_severity(severity):
    result = notification_bus._normalize_payload({"severity": severity})

    assert result["severity"] == severity


def test_normalize_payload_rejects_invalid_severity():
    with pytest.raises(ValueError, match="Invalid severity"):
        notification_bus._normalize_payload({"severity": "urgent"})


def test_normalize_payload_preserves_optional_fields():
    payload = {
        "title": "Изменение закона",
        "message": "Изменились правила.",
        "severity": "high",
        "notification_type": "law_change",
        "id": 123,
        "meta": {"law_id": 7},
        "user_id": 42,
        "timestamp": "2026-10-09T10:00:00+00:00",
    }

    result = notification_bus._normalize_payload(payload)

    assert result["title"] == "Изменение закона"
    assert result["message"] == "Изменились правила."
    assert result["type"] == "law_change"
    assert result["id"] == 123
    assert result["meta"] == {"law_id": 7}
    assert result["user_id"] == 42
    assert result["timestamp"] == "2026-10-09T10:00:00+00:00"