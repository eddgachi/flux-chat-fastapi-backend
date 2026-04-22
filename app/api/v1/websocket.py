"""
WebSocket endpoint.

Supported client → server message types:
  send_message   – send a chat message
  typing_start   – user started typing
  typing_stop    – user stopped typing
  ping           – heartbeat (refreshes presence TTL); server replies with pong
  mark_read      – mark a message as read (data.message_id required)

Server → client broadcast types (via Redis pub/sub):
  connection_established
  new_message
  message_updated
  message_deleted
  read_receipt
  typing_start / typing_stop
  user_online / user_offline
  pong
  error
"""

import json
import logging

from fastapi import Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.connection_manager import manager
from app.core.metrics import websocket_messages_received
from app.core.redis_listener import redis_listener
from app.core.security import decode_access_token
from app.db.session import AsyncSessionLocal, get_db
from app.services import chat_service, message_service, presence_service, user_service
from app.services.websocket_service import websocket_service

logger = logging.getLogger(__name__)


class WebSocketAuthError(Exception):
    pass


async def authenticate_websocket(websocket: WebSocket, token: str) -> int:
    if not token:
        raise WebSocketAuthError("Missing authentication token")

    payload = decode_access_token(token)
    if not payload:
        raise WebSocketAuthError("Invalid or expired token")

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise WebSocketAuthError("Invalid token payload")

    try:
        return int(user_id_str)
    except ValueError:
        raise WebSocketAuthError("Invalid user ID in token")


async def verify_chat_access(db: AsyncSession, chat_id: int, user_id: int) -> bool:
    return await chat_service.is_participant(db, chat_id, user_id)


async def websocket_endpoint(
    websocket: WebSocket, chat_id: int, token: str, db: AsyncSession = Depends(get_db)
):
    """
    WebSocket endpoint for real-time messaging.
    URL: ws://host/ws/{chat_id}?token={jwt_token}
    """
    try:
        user_id = await authenticate_websocket(websocket, token)
    except WebSocketAuthError as e:
        await websocket.close(code=1008, reason=str(e))
        return

    if not await verify_chat_access(db, chat_id, user_id):
        await websocket.close(code=1008, reason="Access denied to this chat")
        return

    user = await user_service.get_user_by_id(db, user_id)
    username = user.username if user else "Unknown"

    await manager.connect(chat_id, websocket, user_id)
    await redis_listener.subscribe_to_chat(chat_id)

    # Mark user online and notify chat participants
    await presence_service.set_online(user_id)
    await manager.publish_to_redis(
        chat_id,
        {"type": "user_online", "data": {"user_id": user_id, "username": username}},
    )

    await manager.send_personal_message(
        websocket,
        {
            "type": "connection_established",
            "data": {"chat_id": chat_id, "user_id": user_id, "username": username},
        },
    )

    try:
        while True:
            data = await websocket.receive_text()
            websocket_messages_received.labels(chat_id=str(chat_id)).inc()

            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                await manager.send_personal_message(
                    websocket, {"type": "error", "data": {"message": "Invalid JSON"}}
                )
                continue

            msg_type = msg.get("type")
            msg_data = msg.get("data", {})

            # ------------------------------------------------------------------
            # send_message
            # ------------------------------------------------------------------
            if msg_type == "send_message":
                content = msg_data.get("content", "")
                if not isinstance(content, str) or not content.strip():
                    await manager.send_personal_message(
                        websocket,
                        {"type": "error", "data": {"message": "Message content is required"}},
                    )
                    continue

                async with AsyncSessionLocal() as db_session:
                    success = await websocket_service.process_and_broadcast(
                        db=db_session,
                        chat_id=chat_id,
                        sender_id=user_id,
                        content=content.strip(),
                    )

                if not success:
                    await manager.send_personal_message(
                        websocket,
                        {"type": "error", "data": {"message": "Failed to send message"}},
                    )

            # ------------------------------------------------------------------
            # typing_start / typing_stop
            # ------------------------------------------------------------------
            elif msg_type in ("typing_start", "typing_stop"):
                await manager.publish_to_redis(
                    chat_id,
                    {
                        "type": msg_type,
                        "data": {"user_id": user_id, "username": username},
                    },
                )

            # ------------------------------------------------------------------
            # ping (heartbeat) → pong
            # ------------------------------------------------------------------
            elif msg_type == "ping":
                await presence_service.refresh_presence(user_id)
                await manager.send_personal_message(websocket, {"type": "pong", "data": {}})

            # ------------------------------------------------------------------
            # mark_read — mark a message as read and broadcast receipt
            # ------------------------------------------------------------------
            elif msg_type == "mark_read":
                message_id = msg_data.get("message_id")
                if not isinstance(message_id, int):
                    await manager.send_personal_message(
                        websocket,
                        {"type": "error", "data": {"message": "message_id (int) required"}},
                    )
                    continue

                async with AsyncSessionLocal() as db_session:
                    target_msg = await message_service.get_message_by_id(db_session, message_id)
                    if target_msg and target_msg.chat_id == chat_id:
                        receipt = await message_service.mark_message_read(
                            db_session, message_id, user_id
                        )
                        await manager.publish_to_redis(
                            chat_id,
                            {
                                "type": "read_receipt",
                                "data": {
                                    "message_id": message_id,
                                    "user_id": user_id,
                                    "read_at": receipt.read_at.isoformat(),
                                },
                            },
                        )

            else:
                await manager.send_personal_message(
                    websocket,
                    {"type": "error", "data": {"message": f"Unknown message type: {msg_type}"}},
                )

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Unexpected WebSocket error for user {user_id}: {e}")
    finally:
        manager.disconnect(chat_id, websocket, user_id)

        if chat_id not in manager.active_connections or not manager.active_connections[chat_id]:
            await redis_listener.unsubscribe_from_chat(chat_id)

        # Only mark offline if the user has no other sockets open on this instance
        if not manager.user_is_connected(user_id):
            await presence_service.set_offline(user_id)
            await manager.publish_to_redis(
                chat_id,
                {"type": "user_offline", "data": {"user_id": user_id, "username": username}},
            )

        logger.info(f"User {user_id} disconnected from chat {chat_id}")
