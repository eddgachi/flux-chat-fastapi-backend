from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)


class LoginRequest(BaseModel):
    username_or_email: str
    password: str


class UserResponse(UserBase):
    id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserInDB(UserResponse):
    hashed_password: str


class UserSearchResult(BaseModel):
    id: int
    username: str

    class Config:
        from_attributes = True


class PresenceResponse(BaseModel):
    user_id: int
    is_online: bool
    last_seen_at: Optional[datetime] = None
