import asyncio
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from jose import JWTError, jwt
from sqlalchemy import select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.user import User
from app.services.notification_bus import stream_notifications

router = APIRouter(prefix="/api/ws", tags=["Notifications WS"])
logger = logging.getLogger(__name__)


async def _get_user_from_ws_token(token: str | None) -> User | None:
    if not token:
        return None

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None

    email = payload.get("sub")
    if not email or not isinstance(email, str):
        return None

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()


@router.websocket("/notifications")
async def notifications_ws(
    websocket: WebSocket,
    token: str | None = Query(default=None),
):
    user = await _get_user_from_ws_token(token)
    if user is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
        return

    await websocket.accept()
    logger.info("Notification WS connected: user_id=%s", user.id)

    stop_event = asyncio.Event()

    async def send_payload(payload: dict):
        await websocket.send_json(payload)

    stream_task = asyncio.create_task(stream_notifications(user.id, send_payload, stop_event))
    heartbeat_task = asyncio.create_task(_heartbeat(websocket, stop_event))

    try:
        # Keep socket alive and detect disconnects from client side.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info("Notification WS disconnected: user_id=%s", user.id)
    finally:
        stop_event.set()
        for task in (stream_task, heartbeat_task):
            task.cancel()
        await asyncio.gather(stream_task, heartbeat_task, return_exceptions=True)


async def _heartbeat(websocket: WebSocket, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        await asyncio.sleep(30)
        if stop_event.is_set():
            break
        await websocket.send_json({"type": "ping"})
