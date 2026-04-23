"""
Redis Pub/Sub bus for real-time notifications.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from redis import Redis
from redis.asyncio import Redis as AsyncRedis

from app.core.config import settings

logger = logging.getLogger(__name__)

NOTIFICATION_SEVERITIES = {"low", "medium", "high", "critical"}
NOTIFICATION_CHANNEL_PREFIX = "notifications"
NOTIFICATION_BROADCAST_CHANNEL = f"{NOTIFICATION_CHANNEL_PREFIX}:broadcast"


def build_user_channel(user_id: int) -> str:
    return f"{NOTIFICATION_CHANNEL_PREFIX}:{user_id}"


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    severity = payload.get("severity", "medium")
    if severity not in NOTIFICATION_SEVERITIES:
        raise ValueError(
            f"Invalid severity '{severity}'. Allowed: {sorted(NOTIFICATION_SEVERITIES)}"
        )

    normalized = {
        "title": payload.get("title", "Новое уведомление"),
        "message": payload.get("message", ""),
        "severity": severity,
        "type": payload.get("type", payload.get("notification_type", "system")),
        "timestamp": payload.get("timestamp")
        or datetime.now(timezone.utc).isoformat(),
    }

    if "meta" in payload:
        normalized["meta"] = payload["meta"]
    if "id" in payload:
        normalized["id"] = payload["id"]
    if "user_id" in payload:
        normalized["user_id"] = payload["user_id"]

    return normalized


async def publish_notification_async(
    payload: dict[str, Any],
    *,
    user_id: int | None = None,
    channel: str | None = None,
) -> None:
    """
    Publish notification to Redis from async context.
    Priority: explicit channel > user_id channel > broadcast channel.
    """
    message = _normalize_payload(payload)
    target_channel = channel or (
        build_user_channel(user_id) if user_id is not None else NOTIFICATION_BROADCAST_CHANNEL
    )

    client = AsyncRedis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        await client.publish(target_channel, json.dumps(message, ensure_ascii=False))
    finally:
        await client.aclose()


def publish_notification(
    payload: dict[str, Any],
    *,
    user_id: int | None = None,
    channel: str | None = None,
) -> None:
    """
    Publish notification to Redis from sync context (e.g. Celery tasks).
    """
    message = _normalize_payload(payload)
    target_channel = channel or (
        build_user_channel(user_id) if user_id is not None else NOTIFICATION_BROADCAST_CHANNEL
    )

    client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        client.publish(target_channel, json.dumps(message, ensure_ascii=False))
    finally:
        client.close()


async def stream_notifications(
    user_id: int,
    sender: Any,
    stop_event: asyncio.Event,
) -> None:
    """
    Subscribe to user + broadcast channels and call sender(payload_dict).
    """
    client = AsyncRedis.from_url(settings.REDIS_URL, decode_responses=True)
    pubsub = client.pubsub(ignore_subscribe_messages=True)
    channels = [build_user_channel(user_id), NOTIFICATION_BROADCAST_CHANNEL]

    try:
        await pubsub.subscribe(*channels)
        logger.info("WS subscribed to channels=%s", channels)

        while not stop_event.is_set():
            message = await pubsub.get_message(timeout=1.0)
            if not message or message.get("type") != "message":
                continue

            raw_data = message.get("data")
            if not raw_data:
                continue

            try:
                payload = json.loads(raw_data)
            except json.JSONDecodeError:
                logger.warning("Invalid notification JSON in Redis: %s", raw_data)
                continue

            severity = payload.get("severity")
            if severity not in NOTIFICATION_SEVERITIES:
                logger.warning("Skipped notification with invalid severity: %s", severity)
                continue

            await sender(payload)
    finally:
        await pubsub.unsubscribe(*channels)
        await pubsub.aclose()
        await client.aclose()
