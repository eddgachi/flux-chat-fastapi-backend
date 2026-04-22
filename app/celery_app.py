import logging

from celery import Celery

from app.core.config import settings

# Configure logging for Celery
logger = logging.getLogger(__name__)

# Create Celery instance
celery_app = Celery(
    "chat_backend",
    broker=settings.REDIS_URL,  # Redis as message broker
    backend=None,  # We don't need result backend for notifications
    include=["app.tasks.notifications"],  # Task modules to import
)

# Celery configuration
celery_app.conf.update(
    # Task serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Task execution
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    # Worker prefetch (how many tasks to grab at once)
    worker_prefetch_multiplier=1,  # Fair distribution
    # Task routing (optional)
    task_default_queue="default",
    task_default_exchange="default",
    task_default_routing_key="default",
    # Retry policy for failed tasks
    task_acks_late=True,  # Acknowledge after task completion
    task_reject_on_worker_lost=True,
    # Rate limiting (optional)
    task_annotations={
        "app.tasks.notifications.send_push_notification": {
            "rate_limit": "10/m"  # Max 10 notifications per minute
        }
    },
)

# Optional: Configure logging
celery_app.conf.worker_redirect_stdouts_level = "INFO"

if __name__ == "__main__":
    celery_app.start()
