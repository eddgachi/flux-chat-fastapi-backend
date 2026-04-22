import asyncio
import json
import logging
from ast import Set

import redis.asyncio as redis

from app.core.config import settings
from app.core.connection_manager import manager

logger = logging.getLogger(__name__)


class RedisMessageListener:
    """
    Background task that listens for Redis pub/sub messages and forwards them
    to local WebSocket connections.
    """

    def __init__(self):
        self.redis_client = None
        self.pubsub = None
        self.running = False
        self.task = None
        self.subscribed_chats: Set[int] = set()

    async def start(self):
        """Start the Redis listener in the background."""
        if self.running:
            return

        self.redis_client = await redis.from_url(
            settings.REDIS_URL, encoding="utf-8", decode_responses=True
        )
        self.pubsub = self.redis_client.pubsub()

        self.running = True
        self.task = asyncio.create_task(self._listen())
        logger.info("Redis message listener started")

    async def stop(self):
        """Stop the Redis listener."""
        self.running = False

        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

        if self.pubsub:
            await self.pubsub.close()
        if self.redis_client:
            await self.redis_client.close()

        logger.info("Redis message listener stopped")

    async def subscribe_to_chat(self, chat_id: int):
        """
        Subscribe to a chat's Redis channel.
        Called when first client connects to a chat on this instance.
        """
        if not self.pubsub:
            logger.warning("Redis pubsub not initialized yet")
            return

        if chat_id in self.subscribed_chats:
            return

        channel = f"chat:{chat_id}"
        await self.pubsub.subscribe(channel)
        self.subscribed_chats.add(chat_id)
        logger.info(f"Subscribed to Redis channel: {channel}")

    async def unsubscribe_from_chat(self, chat_id: int):
        """
        Unsubscribe from a chat's Redis channel.
        Called when last client disconnects from a chat on this instance.
        """
        if not self.pubsub:
            return

        if chat_id not in self.subscribed_chats:
            return

        channel = f"chat:{chat_id}"
        await self.pubsub.unsubscribe(channel)
        self.subscribed_chats.discard(chat_id)
        logger.info(f"Unsubscribed from Redis channel: {channel}")

    async def _listen(self):
        """Main listening loop."""
        while self.running:
            try:
                # Skip if no channels subscribed (pubsub connection not established)
                if not self.subscribed_chats:
                    await asyncio.sleep(0.1)
                    continue

                message = await self.pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )

                if message and message.get("type") == "message":
                    channel = message.get("channel")
                    if channel and channel.startswith("chat:"):
                        chat_id = int(channel.split(":")[1])
                        data = json.loads(message.get("data", "{}"))

                        # Broadcast to local connections only
                        await manager.broadcast_to_local_chat(chat_id, data)
                        logger.debug(
                            f"Forwarded Redis message to chat {chat_id} local connections"
                        )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in Redis listener: {e}", exc_info=True)
                await asyncio.sleep(1)


# Global listener instance
redis_listener = RedisMessageListener()
