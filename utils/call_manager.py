import json
import os
from uuid import UUID

import redis.asyncio as redis

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
redis_client = None


async def get_redis():
    global redis_client
    if redis_client is None:
        redis_client = await redis.from_url(REDIS_URL, decode_responses=True)
    return redis_client


CALL_TTL = 300  # 5 minutes – call state expires if not completed


async def set_call_state(call_id: UUID, state: dict):
    r = await get_redis()
    await r.setex(f"call:{call_id}", CALL_TTL, json.dumps(state))


async def get_call_state(call_id: UUID) -> dict | None:
    r = await get_redis()
    data = await r.get(f"call:{call_id}")
    return json.loads(data) if data else None


async def delete_call_state(call_id: UUID):
    r = await get_redis()
    await r.delete(f"call:{call_id}")
