import logging
from datetime import datetime
from typing import Any, Dict

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="send_push_notification",
    max_retries=3,
    default_retry_delay=60,  # Retry after 60 seconds if fails
)
def send_push_notification(self, user_id: int, message_data: Dict[str, Any]):
    """
    Simulate sending a push notification to a user.
    In production, this would integrate with Firebase Cloud Messaging (FCM),
    Apple Push Notification Service (APNS), or a webhook.
    """
    try:
        logger.info(f"Sending push notification to user {user_id}")
        logger.info(f"Message data: {message_data}")

        # Simulate API call to push notification service
        # In production, you would call FCM/APNS/Expo here

        # Simulate potential failure (for testing retries)
        # if message_data.get("content") == "fail":
        #     raise Exception("Simulated push notification failure")

        # Log success
        logger.info(f"Push notification sent successfully to user {user_id}")

        # Return result for monitoring
        return {
            "status": "success",
            "user_id": user_id,
            "sent_at": datetime.utcnow().isoformat(),
            "message_preview": message_data.get("content", "")[:50],
        }

    except Exception as e:
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
    try:
        logger.info(f"Sending email to {user_email}")
        logger.info(f"New message from {sender_name}: {message_preview}")

        # Simulate email sending (would use SMTP or email service API)

        return {
            "status": "success",
            "email": user_email,
            "sent_at": datetime.utcnow().isoformat(),
        }

    except Exception as e:
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
