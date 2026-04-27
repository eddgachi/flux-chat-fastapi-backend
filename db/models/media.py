import enum
from uuid import uuid4

from sqlalchemy import Column, DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID

from db.session import Base


class MediaType(str, enum.Enum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"


class Media(Base):
    __tablename__ = "media"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    type = Column(SQLEnum(MediaType), nullable=False)
    storage_path = Column(String, nullable=False)  # relative path or S3 key
    thumbnail_path = Column(String, nullable=True)  # for images/videos
    mime_type = Column(String(100))
    size_bytes = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())
