from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class MessageOut(BaseModel):
    id: UUID
    chat_id: UUID
    sender_id: UUID
    text: Optional[str] = None
    status: str  # sent/delivered/read
    created_at: datetime


class MessageSendWebsocket(BaseModel):
    type: str = "message"
    to_user_id: UUID
    text: str
    temp_id: str  # client-generated ID for optimistic UI


class ReadReceiptWebsocket(BaseModel):
    type: str = "read"
    message_id: UUID
