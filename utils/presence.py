# utils/presence.py
import os
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import redis.asyncio as redis
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.user import User

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
redis_client = None


async def get_redis():
    global redis_client
    if redis_client is None:
        redis_client = await redis.from_url(REDIS_URL, decode_responses=True)
    return redis_client


PRESENCE_TTL = 35  # seconds
HEARTBEAT_INTERVAL = 25  # seconds (client should send every 25s)


async def set_online(user_id: UUID):
    r = await get_redis()
    await r.setex(f"presence:{user_id}", PRESENCE_TTL, "online")


async def set_offline(user_id: UUID):
    r = await get_redis()
    await r.delete(f"presence:{user_id}")


async def is_online(user_id: UUID) -> bool:
    r = await get_redis()
    return await r.exists(f"presence:{user_id}") == 1


async def update_last_seen(user_id: UUID, db: AsyncSession):
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(last_seen=datetime.now(timezone.utc))
    )
    await db.commit()


async def get_last_seen(user_id: UUID) -> Optional[datetime]:
    # If online, return None (or we can return None meaning currently online)
    # For offline, we need last_seen from DB. We'll store last_seen in DB only on disconnect.
    # For simplicity, we'll maintain last_seen in DB user table? We can add a column.
    # But we can also store last_seen in Redis as a separate key.
    # Better: when user goes offline, update DB. When online, we don't update DB continuously.
    # We'll query DB for last_seen. However, we didn't add last_seen column yet.
    # Let's add last_seen to users table.
    pass
