from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class BackupMetadata(BaseModel):
    user_id: UUID
    phone_number: str
    export_date: datetime
    version: str = "1.0"
    chat_count: int
    message_count: int


class BackupExportResponse(BaseModel):
    backup_id: str
    download_url: str
    expires_at: datetime


class BackupRestoreRequest(BaseModel):
    backup_file_url: str
    decryption_key: Optional[str] = None
