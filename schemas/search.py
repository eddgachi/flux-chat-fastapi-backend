from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class MessageSearchResult(BaseModel):
    id: UUID
    chat_id: UUID
    chat_name: Optional[str]  # for private: other user's name, for group: group name
    sender_name: str
    text: str
    created_at: datetime
