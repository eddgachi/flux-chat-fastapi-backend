from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class GroupCreate(BaseModel):
    name: str
    avatar_url: Optional[str] = None
    member_ids: List[UUID]  # initial members (at least one besides creator)


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    avatar_url: Optional[str] = None


class GroupOut(BaseModel):
    id: UUID
    name: str
    avatar_url: Optional[str] = None
    created_at: datetime
    participants_count: int


class ParticipantOut(BaseModel):
    user_id: UUID
    name: str
    avatar_url: Optional[str]
    role: str
    joined_at: datetime


class AddParticipant(BaseModel):
    user_id: UUID


class UpdateRole(BaseModel):
    role: str  # "admin" or "member"
