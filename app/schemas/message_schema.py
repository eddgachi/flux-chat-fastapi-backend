from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class MessageBase(BaseModel):
    content: str


class MessageCreate(MessageBase):
    pass


class MessageUpdate(BaseModel):
    content: str = Field(..., min_length=1)


class MessageResponse(MessageBase):
    id: int
    chat_id: int
    sender_id: int
    sent_at: datetime
    edited_at: Optional[datetime] = None
    updated_at: datetime
    is_deleted: bool

    class Config:
        from_attributes = True


class MessageListResponse(BaseModel):
    messages: List[MessageResponse]
    total: int
    skip: int
    limit: int


class CursorMessageListResponse(BaseModel):
    messages: List[MessageResponse]
    next_cursor: Optional[int] = None  # message_id to use as `before` in next request
    has_more: bool


class MessageReadResponse(BaseModel):
    message_id: int
    user_id: int
    read_at: datetime

    class Config:
        from_attributes = True


class UnreadCountResponse(BaseModel):
    chat_id: int
    unread_count: int
