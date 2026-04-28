import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

STORAGE_TYPE = os.getenv("STORAGE_TYPE", "local")
BACKUP_ROOT = Path(os.getenv("BACKUP_ROOT", "/app/backups"))

if STORAGE_TYPE == "local":
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)


async def upload_backup_file(local_path: str, backup_id: str) -> str:
    if STORAGE_TYPE == "local":
        dest = BACKUP_ROOT / backup_id
        shutil.move(local_path, dest)
        # Return a URL that can be used to download (we'll serve via a static route or generate signed URL)
        # For simplicity, we'll create a temporary download endpoint.
        return f"/backup/download/{backup_id}"
    else:
        # S3 implementation: upload and generate presigned URL
        pass
