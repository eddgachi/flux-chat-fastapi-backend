import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from celery import Celery
from sqlalchemy import delete, select

from utils.notifications import send_to_user

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
celery_app = Celery("chat_worker", broker=REDIS_URL, backend=REDIS_URL)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

# ------------------------------------------------------------
# Celery Beat schedule
# ------------------------------------------------------------
celery_app.conf.beat_schedule = {
    "delete-expired-statuses": {
        "task": "celery_worker.delete_expired_statuses",
        "schedule": 3600.0,  # every hour
    },
}
celery_app.conf.timezone = "UTC"

# ------------------------------------------------------------
# Media processing configuration
# ------------------------------------------------------------
STORAGE_TYPE = os.getenv("STORAGE_TYPE", "local")  # 'local' or 's3'
MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", "/app/media_storage"))
ORIGINALS_DIR = MEDIA_ROOT / "originals"
THUMBNAILS_DIR = MEDIA_ROOT / "thumbnails"

# Ensure directories exist
ORIGINALS_DIR.mkdir(parents=True, exist_ok=True)
THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)


def generate_thumbnail(
    input_path: Path, output_path: Path, media_type: str, size=(200, 200)
):
    if media_type == "image":
        from PIL import Image

        img = Image.open(input_path)
        img.thumbnail(size)
        img.save(output_path)
    elif media_type == "video":
        import ffmpeg

        # Use ffmpeg to extract frame at 1 second
        (
            ffmpeg.input(str(input_path), ss=1)
            .output(str(output_path), vframes=1, format="image2", vcodec="mjpeg")
            .run(quiet=True, overwrite_output=True)
        )
    # Audio and documents don't get thumbnails


@celery_app.task
def process_media(media_id: str, original_path: str, media_type: str, mime_type: str):
    """
    Generates thumbnail (if applicable) and moves file to final storage.
    Updates database with storage_path and thumbnail_path.
    """
    import asyncio
    import shutil

    from db.models.media import Media
    from db.session import AsyncSessionLocal

    async def _process():
        async with AsyncSessionLocal() as db:
            media = await db.get(Media, UUID(media_id))
            if not media:
                return

            # Define final storage paths
            if STORAGE_TYPE == "local":
                final_original = (
                    ORIGINALS_DIR / f"{media_id}_{Path(original_path).name}"
                )
                shutil.move(original_path, final_original)
                media.storage_path = str(final_original.relative_to(MEDIA_ROOT))

                if media_type in ("image", "video"):
                    thumb_filename = f"thumb_{media_id}.jpg"
                    thumb_path = THUMBNAILS_DIR / thumb_filename
                    generate_thumbnail(final_original, thumb_path, media_type)
                    media.thumbnail_path = str(thumb_path.relative_to(MEDIA_ROOT))
            else:
                # S3 implementation would go here using boto3
                pass

            await db.commit()

    asyncio.run(_process())


@celery_app.task
def delete_expired_statuses():
    """Delete statuses with expires_at < now() and associated views."""
    import asyncio

    from db.models.status import Status, StatusView
    from db.session import AsyncSessionLocal

    async def _clean():
        async with AsyncSessionLocal() as db:
            now = datetime.now(timezone.utc)
            # Delete views first (cascade not automatic if we delete manually)
            stmt_views = delete(StatusView).where(
                StatusView.status_id.in_(
                    select(Status.id).where(Status.expires_at < now)
                )
            )
            await db.execute(stmt_views)
            stmt = delete(Status).where(Status.expires_at < now)
            result = await db.execute(stmt)
            await db.commit()
            return result.rowcount

    return asyncio.run(_clean())


@celery_app.task
def send_message_notification(
    user_id: str, sender_name: str, message_preview: str, chat_id: str
):
    import asyncio

    from db.session import AsyncSessionLocal

    async def _send():
        async with AsyncSessionLocal() as db:
            await send_to_user(
                UUID(user_id),
                sender_name,
                message_preview,
                {"chat_id": chat_id, "type": "message"},
                db,
            )

    asyncio.run(_send())
