from typing import Dict
from uuid import UUID

from fastapi import WebSocket


class ConnectionManager:
    """Single-instance WebSocket connection manager."""

    def __init__(self):
        self.active_connections: Dict[UUID, WebSocket] = {}

    async def connect(self, user_id: UUID, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: UUID):
        self.active_connections.pop(user_id, None)

    async def send_personal_message(self, user_id: UUID, message: dict):
        ws = self.active_connections.get(user_id)
        if ws:
            await ws.send_json(message)
            return True
        return False

    def is_online(self, user_id: UUID) -> bool:
        return user_id in self.active_connections


manager = ConnectionManager()
