from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class UserOut(BaseModel):
    id: UUID
    phone_number: str
    name: str | None
    avatar_url: str | None
    created_at: datetime


class UserUpdate(BaseModel):
    name: str | None = None
    avatar_url: str | None = None
