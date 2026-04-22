from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_app import celery_app
from app.db.session import get_db

router = APIRouter()


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    # Test database connectivity
    try:
        await db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"

    # Test Celery connectivity (optional)
    try:
        # Ping Celery worker
        celery_status = "ok" if celery_app.control.ping(timeout=1.0) else "no_workers"
    except Exception:
        celery_status = "unavailable"

    return {"status": "ok", "database": db_status, "celery": celery_status}
