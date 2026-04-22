import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.connection_manager import manager
from app.services import chat_service, message_service

logger = logging.getLogger(__name__)


class WebSocketService:
    """Handles WebSocket connections and message broadcasting."""

    @staticmethod
    async def process_and_broadcast(
        db: AsyncSession, chat_id: int, sender_id: int, content: str
    ):
        """
        Save message to database and broadcast to all instances via Redis.
        Each instance will then broadcast to its local connections.
        """
        # 1. Verify user is participant (security check)
        is_participant = await chat_service.is_participant(db, chat_id, sender_id)
        if not is_participant:
            logger.warning(
                f"User {sender_id} attempted to send message to chat {chat_id} without permission"
            )
            return False

        # 2. Save message to database
        message = await message_service.create_message(
            db=db, chat_id=chat_id, sender_id=sender_id, content=content
        )

        # 3. Prepare broadcast message
        broadcast_data = {
            "type": "new_message",
            "data": {
                "id": message.id,
                "chat_id": message.chat_id,
                "sender_id": message.sender_id,
                "content": message.content,
                "sent_at": message.sent_at.isoformat() if message.sent_at else None,
                "updated_at": (
                    message.updated_at.isoformat() if message.updated_at else None
                ),
            },
        }

        # 4. Publish to Redis (all instances will receive and broadcast locally)
        await manager.publish_to_redis(chat_id, broadcast_data)

        # 5. Also broadcast locally for this instance (optimization)
        #    This avoids going through Redis for local clients
        await manager.broadcast_to_local_chat(chat_id, broadcast_data)

        logger.info(
            f"Message {message.id} published to Redis and broadcasted locally for chat {chat_id}"
        )
        return True


websocket_service = WebSocketService()
