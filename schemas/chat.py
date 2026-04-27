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
    # For list view, we will add last_message later (can be computed separately)
