import enum
from uuid import uuid4

from sqlalchemy import Column, DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import UUID

from db.session import Base


class CallType(str, enum.Enum):
    AUDIO = "audio"
    VIDEO = "video"


class CallStatus(str, enum.Enum):
    RINGING = "ringing"
    ACTIVE = "active"
    ENDED = "ended"
    REJECTED = "rejected"
    MISSED = "missed"


class Call(Base):
    __tablename__ = "calls"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    initiator_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    receiver_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    call_type = Column(SQLEnum(CallType), nullable=False)
    status = Column(SQLEnum(CallStatus), default=CallStatus.RINGING)
    started_at = Column(DateTime, server_default=func.now())
    ended_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)  # computed on end
