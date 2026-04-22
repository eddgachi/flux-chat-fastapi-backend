"""
Redis-based presence tracking.

Strategy:
  - On WS connect:    SET presence:{user_id} 1 EX {TTL}
  - On WS disconnect: DEL presence:{user_id}
  - On WS ping:       EXPIRE presence:{user_id} {TTL}   (heartbeat refresh)
  - Check presence:   EXISTS presence:{user_id}

TTL is intentionally short so stale "online" states auto-expire if the client
crashes without sending a disconnect (e.g. network loss).
"""

import logging
from datetime import datetime
from typing import Dict, List

import redis.asyncio as aioredis

from app.core.config import settings
from app.db.models.user import User
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

PRESENCE_TTL = 60  # seconds; client must heartbeat within this window
PRESENCE_KEY = "presence:{user_id}"


def _key(user_id: int) -> str:
    return PRESENCE_KEY.format(user_id=user_id)


async def _get_redis() -> aioredis.Redis:
    return await aioredis.from_url(
        settings.REDIS_URL, encoding="utf-8", decode_responses=True
    )


async def set_online(user_id: int) -> None:
    r = await _get_redis()
    try:
        await r.set(_key(user_id), "1", ex=PRESENCE_TTL)
        await _update_last_seen_db(user_id)
    finally:
        await r.aclose()


async def set_offline(user_id: int) -> None:
    r = await _get_redis()
    try:
        await r.delete(_key(user_id))
        await _update_last_seen_db(user_id)
    finally:
        await r.aclose()


async def refresh_presence(user_id: int) -> None:
    """Called on heartbeat ping to extend the TTL."""
    r = await _get_redis()
    try:
        await r.expire(_key(user_id), PRESENCE_TTL)
    finally:
        await r.aclose()


async def is_online(user_id: int) -> bool:
    r = await _get_redis()
    try:
        return bool(await r.exists(_key(user_id)))
    finally:
        await r.aclose()


async def get_presence_for_users(user_ids: List[int]) -> Dict[int, bool]:
    """Bulk-check presence for a list of users using a pipeline."""
    if not user_ids:
        return {}
    r = await _get_redis()
    try:
        async with r.pipeline(transaction=False) as pipe:
            for uid in user_ids:
                pipe.exists(_key(uid))
            results = await pipe.execute()
        return {uid: bool(exists) for uid, exists in zip(user_ids, results)}
    finally:
        await r.aclose()


async def _update_last_seen_db(user_id: int) -> None:
    """Persist last_seen_at to the DB (best-effort; never raises)."""
    try:
        from sqlalchemy import select, update

        async with AsyncSessionLocal() as db:
            await db.execute(
                update(User)
                .where(User.id == user_id)
                .values(last_seen_at=datetime.utcnow())
            )
            await db.commit()
    except Exception as e:
        logger.warning(f"Could not update last_seen_at for user {user_id}: {e}")
