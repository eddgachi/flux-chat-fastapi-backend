import json
import logging
from typing import Dict, Set

import redis.asyncio as redis
from fastapi import WebSocket

from app.core.config import settings
from app.core.metrics import (
    active_chats_gauge,
    websocket_connections_active,
    websocket_connections_total,
    websocket_messages_sent,
)

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages local WebSocket connections and publishes to Redis.
    """

    def __init__(self):
        self.active_connections: Dict[int, Set[WebSocket]] = {}
        # Tracks how many open sockets each user has across all chats
        self._user_connection_count: Dict[int, int] = {}
        self.redis_client: redis.Redis = None

    async def initialize_redis(self):
        """Initialize Redis client for publishing."""
        self.redis_client = await redis.from_url(
            settings.REDIS_URL, encoding="utf-8", decode_responses=True
        )
        logger.info("Redis publisher initialized")

    async def close_redis(self):
        """Close Redis connection."""
        if self.redis_client:
            await self.redis_client.close()
            logger.info("Redis publisher closed")

    async def connect(self, chat_id: int, websocket: WebSocket, user_id: int):
        """Accept and store a new WebSocket connection."""
        await websocket.accept()

        if chat_id not in self.active_connections:
            self.active_connections[chat_id] = set()

        self.active_connections[chat_id].add(websocket)
        self._user_connection_count[user_id] = self._user_connection_count.get(user_id, 0) + 1

        websocket_connections_total.labels(chat_id=str(chat_id)).inc()
        websocket_connections_active.labels(chat_id=str(chat_id)).inc()
        active_chats_gauge.set(len(self.active_connections))

        logger.info(
            f"Client connected to chat {chat_id}. Local connections: {len(self.active_connections[chat_id])}"
        )

    def disconnect(self, chat_id: int, websocket: WebSocket, user_id: int):
        """Remove a WebSocket connection."""
        if chat_id in self.active_connections:
            self.active_connections[chat_id].discard(websocket)
            websocket_connections_active.labels(chat_id=str(chat_id)).dec()

            if not self.active_connections[chat_id]:
                del self.active_connections[chat_id]
                active_chats_gauge.set(len(self.active_connections))

        count = self._user_connection_count.get(user_id, 1) - 1
        if count <= 0:
            self._user_connection_count.pop(user_id, None)
        else:
            self._user_connection_count[user_id] = count

        logger.info(f"Client disconnected from chat {chat_id}")

    def user_is_connected(self, user_id: int) -> bool:
        """True if the user still has at least one open socket on this instance."""
        return self._user_connection_count.get(user_id, 0) > 0

    async def broadcast_to_local_chat(self, chat_id: int, message: dict):
        """Broadcast a message only to local connections (this instance)."""
        if chat_id not in self.active_connections:
            return

        # Track messages sent
        websocket_messages_sent.labels(chat_id=str(chat_id)).inc(
            len(self.active_connections[chat_id])
        )

        disconnected = []

        for connection in self.active_connections[chat_id]:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error sending to client: {e}")
                disconnected.append(connection)

        # Clean up disconnected clients
        for connection in disconnected:
            self.disconnect(chat_id, connection)

    async def publish_to_redis(self, chat_id: int, message: dict):
        """
        Publish a message to Redis channel for this chat.
        """
        if not self.redis_client:
            logger.error("Redis client not initialized")
            return

        channel = f"chat:{chat_id}"
        try:
            await self.redis_client.publish(channel, json.dumps(message))
            logger.debug(f"Published to Redis channel: {channel}")
        except Exception as e:
            logger.error(f"Error publishing to Redis: {e}")

    async def send_personal_message(self, websocket: WebSocket, message: dict):
        """Send a message to a specific connection."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")


# Global instance
manager = ConnectionManager()
