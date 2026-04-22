import logging
from typing import Dict, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages WebSocket connections per chat.
    In Phase 5, this is in-memory (single instance).
    Phase 6 will add Redis pub/sub for multi-instance support.
    """

    def __init__(self):
        # chat_id -> set of WebSocket connections
        self.active_connections: Dict[int, Set[WebSocket]] = {}

    async def connect(self, chat_id: int, websocket: WebSocket):
        """Accept and store a new WebSocket connection."""
        await websocket.accept()

        if chat_id not in self.active_connections:
            self.active_connections[chat_id] = set()

        self.active_connections[chat_id].add(websocket)
        logger.info(
            f"Client connected to chat {chat_id}. Total connections: {len(self.active_connections[chat_id])}"
        )

    def disconnect(self, chat_id: int, websocket: WebSocket):
        """Remove a WebSocket connection."""
        if chat_id in self.active_connections:
            self.active_connections[chat_id].discard(websocket)

            # Clean up empty chat rooms
            if not self.active_connections[chat_id]:
                del self.active_connections[chat_id]

            logger.info(f"Client disconnected from chat {chat_id}")

    async def broadcast_to_chat(self, chat_id: int, message: dict):
        """
        Broadcast a message to all connected clients in a specific chat.
        """
        if chat_id not in self.active_connections:
            logger.info(f"No active connections for chat {chat_id}")
            return

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

    async def send_personal_message(self, websocket: WebSocket, message: dict):
        """Send a message to a specific connection."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")


# Global instance
manager = ConnectionManager()
