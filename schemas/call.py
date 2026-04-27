from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CallHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    initiator_id: UUID
    receiver_id: UUID
    call_type: str
    status: str
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
