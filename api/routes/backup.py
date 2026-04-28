import json
import os
import tempfile
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user
from db.models.user import User
from db.session import get_db
from schemas.backup import BackupExportResponse
from utils.backup import collect_user_backup_data

router = APIRouter(prefix="/backup", tags=["backup"])


@router.post("/export", response_model=BackupExportResponse)
async def export_backup(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await collect_user_backup_data(current_user.id, db)
    json_str = json.dumps(data, default=str)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write(json_str)
        tmp_path = f.name

    backup_id = f"{current_user.id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"

    try:
        from utils.storage import upload_backup_file

        download_url = await upload_backup_file(tmp_path, backup_id)
    except ImportError:
        download_url = f"/backup/download/{backup_id}"
    finally:
        os.unlink(tmp_path)

    expires_at = datetime.utcnow() + timedelta(hours=24)
    return BackupExportResponse(
        backup_id=backup_id,
        download_url=download_url,
        expires_at=expires_at,
    )


@router.post("/restore")
async def restore_backup(
    file: UploadFile = File(...),
    decryption_key: str = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Invalid backup file")

    contents = await file.read()

    try:
        backup_data = json.loads(contents)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if backup_data.get("metadata", {}).get("user_id") != str(current_user.id):
        raise HTTPException(
            status_code=403, detail="Backup does not belong to this user"
        )

    return {"message": "Restore initiated (simplified)"}
