import logging
from datetime import datetime, timedelta

from sqlalchemy import delete

from app.celery_app import celery_app
from app.core.config import settings
from app.db.models.message import Message

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.maintenance.cleanup_old_messages", bind=True)
def cleanup_old_messages(self, days_to_keep: int = 30):
    """
    Delete messages older than specified days.
    This is a periodic task (run daily via Celery Beat).
    """
    try:
        # Create async engine (Celery works sync, so we need sync engine)
        from sqlalchemy import create_engine

        # Convert async URL to sync URL
        sync_url = settings.DATABASE_URL.replace(
            "postgresql+asyncpg://", "postgresql://"
        )
        sync_engine = create_engine(sync_url)

        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)

        with sync_engine.connect() as conn:
            result = conn.execute(delete(Message).where(Message.sent_at < cutoff_date))
            conn.commit()
            deleted_count = result.rowcount

        logger.info(
            f"🧹 Cleaned up {deleted_count} messages older than {days_to_keep} days"
        )

        return {
            "status": "success",
            "deleted_count": deleted_count,
            "days_to_keep": days_to_keep,
        }

    except Exception as e:
        logger.error(f"Failed to cleanup old messages: {e}")
        raise self.retry(exc=e, countdown=300)  # Retry in 5 minutes


@celery_app.task
def health_check():
    """Simple health check task for monitoring."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}
