import enum
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID

from db.session import Base


class StatusPrivacy(str, enum.Enum):
    MY_CONTACTS = "my_contacts"
    CLOSE_FRIENDS = "close_friends"
    # we'll use contacts as default


class Status(Base):
    __tablename__ = "statuses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    media_id = Column(
        UUID(as_uuid=True), ForeignKey("media.id", ondelete="SET NULL"), nullable=True
    )
    text = Column(String(255), nullable=True)
    privacy = Column(String(20), default=StatusPrivacy.MY_CONTACTS)
    expires_at = Column(DateTime, nullable=False)  # created_at + 24h
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (Index("ix_statuses_user_expires", "user_id", "expires_at"),)


class StatusView(Base):
    __tablename__ = "status_views"

    status_id = Column(
        UUID(as_uuid=True),
        ForeignKey("statuses.id", ondelete="CASCADE"),
        primary_key=True,
    )
    viewer_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    viewed_at = Column(DateTime, server_default=func.now())
