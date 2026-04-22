import json
import logging

from fastapi import Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.connection_manager import manager
from app.core.redis_listener import redis_listener
from app.core.security import decode_access_token
from app.db.session import get_db
from app.services import chat_service, user_service
from app.services.websocket_service import websocket_service

logger = logging.getLogger(__name__)


class WebSocketAuthError(Exception):
    pass


async def authenticate_websocket(websocket: WebSocket, token: str) -> int:
    """
    Authenticate WebSocket connection using JWT token from query parameter.
    Returns user_id if valid, raises exception otherwise.
    """
    if not token:
        raise WebSocketAuthError("Missing authentication token")

    payload = decode_access_token(token)
    if not payload:
        raise WebSocketAuthError("Invalid or expired token")

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise WebSocketAuthError("Invalid token payload")

    try:
        user_id = int(user_id_str)
        return user_id
    except ValueError:
        raise WebSocketAuthError("Invalid user ID in token")


async def verify_chat_access(db: AsyncSession, chat_id: int, user_id: int) -> bool:
    """Verify user has access to the chat."""
    return await chat_service.is_participant(db, chat_id, user_id)


async def websocket_endpoint(
    websocket: WebSocket, chat_id: int, token: str, db: AsyncSession = Depends(get_db)
):
    """
    WebSocket endpoint for real-time messaging.
    Connection URL: ws://localhost:8000/ws/{chat_id}?token={jwt_token}
    """
    # Authenticate before accepting connection
    try:
        user_id = await authenticate_websocket(websocket, token)
    except WebSocketAuthError as e:
        # Reject the connection
        await websocket.close(code=1008, reason=str(e))
        return

    # Verify chat access
    if not await verify_chat_access(db, chat_id, user_id):
        await websocket.close(code=1008, reason="Access denied to this chat")
        return

    # Get user info for logging
    user = await user_service.get_user_by_id(db, user_id)

    # Accept connection and add to manager
    await manager.connect(chat_id, websocket)

    # Subscribe to Redis channel for this chat (if not already)
    await redis_listener.subscribe_to_chat(chat_id)  # ADD THIS

    # Send confirmation
    await manager.send_personal_message(
        websocket,
        {
            "type": "connection_established",
            "data": {
                "chat_id": chat_id,
                "user_id": user_id,
                "username": user.username if user else "Unknown",
            },
        },
    )

    try:
        # Listen for messages from this client
        while True:
            # Receive message (JSON format)
            data = await websocket.receive_text()

            try:
                message_data = json.loads(data)

                # Validate message structure
                if message_data.get("type") != "send_message":
                    await manager.send_personal_message(
                        websocket,
                        {"type": "error", "data": {"message": "Invalid message type"}},
                    )
                    continue

                content = message_data.get("data", {}).get("content")
                if (
                    not content
                    or not isinstance(content, str)
                    or len(content.strip()) == 0
                ):
                    await manager.send_personal_message(
                        websocket,
                        {
                            "type": "error",
                            "data": {"message": "Message content is required"},
                        },
                    )
                    continue

                # Process message (save to DB and broadcast)
                # Create a new DB session for this operation
                async for db_session in get_db():
                    success = await websocket_service.process_and_broadcast(
                        db=db_session,
                        chat_id=chat_id,
                        sender_id=user_id,
                        content=content.strip(),
                    )
                    break

                if not success:
                    await manager.send_personal_message(
                        websocket,
                        {
                            "type": "error",
                            "data": {"message": "Failed to send message"},
                        },
                    )

            except json.JSONDecodeError:
                await manager.send_personal_message(
                    websocket,
                    {"type": "error", "data": {"message": "Invalid JSON format"}},
                )
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                await manager.send_personal_message(
                    websocket,
                    {"type": "error", "data": {"message": "Internal server error"}},
                )

    except WebSocketDisconnect:
        manager.disconnect(chat_id, websocket)

        # Check if this was the last connection to this chat
        if (
            chat_id not in manager.active_connections
            or not manager.active_connections[chat_id]
        ):
            await redis_listener.unsubscribe_from_chat(chat_id)

        logger.info(f"User {user_id} disconnected from chat {chat_id}")
    except Exception as e:
        logger.error(f"Unexpected error in WebSocket: {e}")
        manager.disconnect(chat_id, websocket)

        # Check if this was the last connection
        if (
            chat_id not in manager.active_connections
            or not manager.active_connections[chat_id]
        ):
            await redis_listener.unsubscribe_from_chat(chat_id)
