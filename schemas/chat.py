from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class ChatOut(BaseModel):
    id: UUID
    type: str
    group_name: Optional[str] = None
    group_avatar: Optional[str] = None
    created_at: datetime
    pinned: bool = False
    archived: bool = False
    last_message: Optional[dict] = None  # could contain text, sender, time
