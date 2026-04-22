import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.connection_manager import manager
from app.core.metrics import messages_sent_total
from app.services import chat_service, message_service, user_service
from app.tasks.notifications import send_push_notification, update_message_analytics

logger = logging.getLogger(__name__)


class WebSocketService:
    """Handles WebSocket connections and message broadcasting."""

    @staticmethod
    async def process_and_broadcast(
        db: AsyncSession, chat_id: int, sender_id: int, content: str
    ):
        """
        Save message to database, broadcast via Redis, and trigger background tasks.
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

        # 3. Get sender info and chat metadata
        sender = await user_service.get_user_by_id(db, sender_id)
        sender_name = sender.username if sender else "Unknown"

        chat = await chat_service.get_chat_with_participants(db, chat_id)
        participants = chat.participants if chat else []
        is_group = chat.is_group if chat else False

        # Track message sent metric
        messages_sent_total.labels(
            chat_id=str(chat_id), is_group=str(is_group)
        ).inc()

        # 4. Prepare broadcast message
        broadcast_data = {
            "type": "new_message",
            "data": {
                "id": message.id,
                "chat_id": message.chat_id,
                "sender_id": message.sender_id,
                "sender_name": sender_name,
                "content": message.content,
                "sent_at": message.sent_at.isoformat() if message.sent_at else None,
                "updated_at": (
                    message.updated_at.isoformat() if message.updated_at else None
                ),
            },
        }

        # 5. Publish to Redis — the Redis listener handles broadcasting to all local
        #    connections (including this instance), which avoids double-delivery.
        await manager.publish_to_redis(chat_id, broadcast_data)

        # 6. Trigger background tasks (non-blocking)
        for participant in participants:
            if participant.user_id != sender_id:
                # Send push notification asynchronously
                send_push_notification.delay(
                    user_id=participant.user_id,
                    message_data={
                        "chat_id": chat_id,
                        "message_id": message.id,
                        "sender_name": sender_name,
                        "content": content[:100],  # Preview
                        "sent_at": message.sent_at.isoformat(),
                    },
                )

        # 7. Update analytics (non-blocking)
        update_message_analytics.delay(
            chat_id=chat_id, message_id=message.id, user_id=sender_id
        )

        logger.info(
            f"Message {message.id} processed. Triggered {len(participants)-1} notifications and analytics update."
        )
        return True


websocket_service = WebSocketService()
