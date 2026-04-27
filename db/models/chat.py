import enum
import uuid

from sqlalchemy import Column, DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID

from db.session import Base


class ChatType(str, enum.Enum):
    PRIVATE = "private"
    GROUP = "group"  # for later


class Chat(Base):
    __tablename__ = "chats"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type = Column(SQLEnum(ChatType), nullable=False, default=ChatType.PRIVATE)
    group_name = Column(String(100), nullable=True)
    group_avatar = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class ChatParticipant(Base):
    __tablename__ = "chat_participants"

    chat_id = Column(
        UUID(as_uuid=True), ForeignKey("chats.id", ondelete="CASCADE"), primary_key=True
    )
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    joined_at = Column(DateTime, server_default=func.now())
    # For future phases: muted_until, role, etc. We'll keep simple for now.
