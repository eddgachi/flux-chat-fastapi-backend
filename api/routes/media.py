import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user
from db.models.media import Media, MediaType
from db.models.user import User
from db.session import get_db
from celery_worker import STORAGE_TYPE, process_media
from utils.media_processor import validate_media_file

router = APIRouter(prefix="/media", tags=["media"])


@router.post("/upload", response_model=dict)
async def upload_media(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Validate file
    mime = validate_media_file(file)
    # Determine media type
    if mime.startswith("image/"):
        media_type = MediaType.IMAGE
    elif mime.startswith("video/"):
        media_type = MediaType.VIDEO
    elif mime.startswith("audio/"):
        media_type = MediaType.AUDIO
    else:
        media_type = MediaType.DOCUMENT

    # Save temp file
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    # Create media record
    media = Media(
        user_id=current_user.id,
        type=media_type,
        storage_path="",  # placeholder
        mime_type=mime,
        size_bytes=len(content),
    )
    db.add(media)
    await db.commit()
    await db.refresh(media)

    # Schedule background processing
    process_media.delay(str(media.id), tmp_path, media_type.value, mime)

    return {
        "media_id": str(media.id),
        "message": "Upload accepted, processing in background",
    }


@router.get("/{media_id}")
async def get_media(
    media_id: str,
    thumbnail: bool = False,
    db: AsyncSession = Depends(get_db),
):
    from uuid import UUID

    media = await db.get(Media, UUID(media_id))
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    if STORAGE_TYPE == "local":
        from fastapi.responses import FileResponse

        base = Path("/app/media_storage")
        if thumbnail and media.thumbnail_path:
            file_path = base / media.thumbnail_path
        else:
            file_path = base / media.storage_path
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(file_path, media_type=media.mime_type)
    else:
        # S3: generate signed URL and redirect
        pass
