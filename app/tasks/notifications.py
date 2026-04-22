import logging
import time
from datetime import datetime
from typing import Any, Dict

from app.celery_app import celery_app
from app.core.metrics import celery_task_duration_seconds, celery_tasks_total

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True, name="send_push_notification", max_retries=3, default_retry_delay=60
)
def send_push_notification(self, user_id: int, message_data: Dict[str, Any]):
    """Simulate sending a push notification to a user."""
    start_time = time.time()
    task_name = "send_push_notification"

    try:
        logger.info(f"Sending push notification to user {user_id}")

        # Simulate API call
        # In production, this would call FCM/APNS

        # Record success metric
        duration = time.time() - start_time
        celery_tasks_total.labels(task_name=task_name, status="success").inc()
        celery_task_duration_seconds.labels(task_name=task_name).observe(duration)

        logger.info(f"Push notification sent successfully to user {user_id}")

        # Return result for monitoring
        return {
            "status": "success",
            "user_id": user_id,
            "sent_at": datetime.utcnow().isoformat(),
            "message_preview": message_data.get("content", "")[:50],
        }

    except Exception as e:
        duration = time.time() - start_time
        celery_tasks_total.labels(task_name=task_name, status="failure").inc()
        celery_task_duration_seconds.labels(task_name=task_name).observe(duration)

        logger.error(f"Failed to send push notification to user {user_id}: {e}")
        # Retry the task
        raise self.retry(exc=e)


@celery_app.task(bind=True, name="send_email_notification", max_retries=2)
def send_email_notification(
    self, user_email: str, message_preview: str, sender_name: str
):
    """
    Simulate sending an email notification for offline users.
    """
    start_time = time.time()
    task_name = "send_email_notification"
    try:
        logger.info(f"Sending email to {user_email}")
        logger.info(f"New message from {sender_name}: {message_preview}")

        # Simulate email sending (would use SMTP or email service API)

        # Record success metric
        duration = time.time() - start_time
        celery_tasks_total.labels(task_name=task_name, status="success").inc()
        celery_task_duration_seconds.labels(task_name=task_name).observe(duration)

        return {
            "status": "success",
            "email": user_email,
            "sent_at": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        duration = time.time() - start_time
        celery_tasks_total.labels(task_name=task_name, status="failure").inc()
        celery_task_duration_seconds.labels(task_name=task_name).observe(duration)

        logger.error(f"Failed to send email to {user_email}: {e}")
        raise self.retry(exc=e)


@celery_app.task(
    name="update_message_analytics", ignore_result=True  # Don't store result
)
def update_message_analytics(chat_id: int, message_id: int, user_id: int):
    """
    Update analytics counters in background.
    Example: Increment message count, update user activity, etc.
    """
    try:
        logger.info(f"Updating analytics for chat {chat_id}, message {message_id}")

        # In production, this would update:
        # - Message count per chat
        # - User activity timestamps
        # - Word count statistics
        # - Sentiment analysis (calling another service)

        logger.info("Analytics updated successfully")

    except Exception as e:
        logger.error(f"Failed to update analytics: {e}")
        # Don't retry analytics tasks (non-critical)
