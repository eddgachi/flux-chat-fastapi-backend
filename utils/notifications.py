import os
from uuid import UUID

import firebase_admin
from firebase_admin import credentials, messaging
from sqlalchemy import select

# Initialize Firebase (only once)
cred_path = os.getenv("FIREBASE_CREDENTIALS", "/app/firebase-credentials.json")
if os.path.exists(cred_path):
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)


async def send_push_notification(
    device_token: str, title: str, body: str, data: dict = None
):
    """Send a push notification via FCM."""
    if not firebase_admin._apps:
        return
    message = messaging.Message(
        notification=messaging.Notification(title=title, body=body),
        data=data or {},
        token=device_token,
    )
    try:
        response = messaging.send(message)
        return response
    except Exception as e:
        print(f"Push notification failed: {e}")
        return None


async def send_to_user(user_id: UUID, title: str, body: str, data: dict, db):
    """Fetch all device tokens for a user and send notification."""
    from db.models.user import UserDevice

    result = await db.execute(
        select(UserDevice.device_token).where(UserDevice.user_id == user_id)
    )
    tokens = result.scalars().all()
    for token in tokens:
        await send_push_notification(token, title, body, data)
        await send_push_notification(token, title, body, data)
