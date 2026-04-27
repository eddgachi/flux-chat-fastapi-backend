import magic
from fastapi import HTTPException, UploadFile

ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "video/mp4",
    "video/quicktime",
    "audio/mpeg",
    "audio/ogg",
    "audio/wav",
    "application/pdf",
    "application/msword",
    "text/plain",
}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


def validate_media_file(file: UploadFile):
    if file.size > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large")
    mime = magic.from_buffer(file.file.read(1024), mime=True)
    file.file.seek(0)
    if mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail="File type not allowed")
    return mime
