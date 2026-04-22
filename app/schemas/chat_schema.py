from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

# from app.schemas.user_schema import UserResponse


class ChatBase(BaseModel):
    title: Optional[str] = None
    is_group: bool = False


class ChatCreate(ChatBase):
    participant_ids: List[int] = []  # IDs of other participants (creator is auto-added)

    @classmethod
    def create_private(cls, other_user_id: int) -> "ChatCreate":
        """Create a ChatCreate instance for a 1-to-1 chat."""
        return cls(is_group=False, participant_ids=[other_user_id])

    @classmethod
    def create_group(cls, title: str, participant_ids: List[int]) -> "ChatCreate":
        """Create a ChatCreate instance for a group chat."""
        return cls(title=title, is_group=True, participant_ids=participant_ids)


class ChatParticipantResponse(BaseModel):
    user_id: int
    joined_at: datetime

    class Config:
        from_attributes = True


class ChatResponse(ChatBase):
    id: int
    created_at: datetime
    updated_at: datetime
    participants: List[ChatParticipantResponse]
    last_message_preview: Optional[str] = None
    last_message_time: Optional[datetime] = None

    class Config:
        from_attributes = True


class AddParticipantRequest(BaseModel):
    user_id: int
