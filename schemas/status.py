from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class StatusCreate(BaseModel):
    text: Optional[str] = None
    media_id: Optional[UUID] = None
    privacy: str = "my_contacts"


class StatusOut(BaseModel):
    id: UUID
    user_id: UUID
    user_name: str
    user_avatar: Optional[str]
    text: Optional[str]
    media_id: Optional[UUID]
    media_url: Optional[str]
    thumbnail_url: Optional[str]
    created_at: datetime
    expires_at: datetime
    viewed: bool


class StatusViewerOut(BaseModel):
    viewer_id: UUID
    viewer_name: str
    viewer_avatar: Optional[str]
    viewed_at: datetime
