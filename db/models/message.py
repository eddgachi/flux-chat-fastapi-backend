import enum
import uuid

from sqlalchemy import Column, DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID

from db.session import Base


class MessageStatus(str, enum.Enum):
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"


class DeliveryStatus(str, enum.Enum):
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"


class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chat_id = Column(
        UUID(as_uuid=True), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False
    )
    sender_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    text = Column(Text, nullable=True)
    media_id = Column(
        UUID(as_uuid=True), nullable=True
    )  # will link to media table later
    status = Column(SQLEnum(MessageStatus), default=MessageStatus.SENT)
    reply_to_id = Column(UUID(as_uuid=True), nullable=True)  # future
    created_at = Column(DateTime, server_default=func.now())


class MessageDelivery(Base):
    __tablename__ = "message_deliveries"

    message_id = Column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    status = Column(SQLEnum(DeliveryStatus), default=DeliveryStatus.SENT)
    delivered_at = Column(DateTime, nullable=True)
    read_at = Column(DateTime, nullable=True)
