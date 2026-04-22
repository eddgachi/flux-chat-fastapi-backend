"""
User discovery endpoints: search users and check presence.
"""

from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.user_schema import PresenceResponse, UserSearchResult
from app.services import presence_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/search", response_model=List[UserSearchResult])
async def search_users(
    q: str = Query(..., min_length=1, max_length=50, description="Username prefix to search"),
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Search for users by username prefix.
    Useful when starting a new chat or adding participants to a group.
    """
    stmt = (
        select(User)
        .where(
            User.username.ilike(f"{q}%"),
            User.id != current_user.id,
            User.is_active.is_(True),
        )
        .order_by(User.username)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/presence", response_model=List[PresenceResponse])
async def get_presence(
    user_ids: str = Query(..., description="Comma-separated list of user IDs"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Bulk-check online/offline status for a list of users.

    Pass `user_ids=1,2,3` in the query string.
    Uses Redis for O(1) lookups per user with a single pipeline.
    """
    try:
        ids = [int(uid.strip()) for uid in user_ids.split(",") if uid.strip()]
    except ValueError:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="user_ids must be a comma-separated list of integers",
        )

    if not ids:
        return []

    # Bulk presence check via Redis pipeline
    presence_map = await presence_service.get_presence_for_users(ids)

    # Fetch last_seen_at from DB for offline users
    stmt = select(User).where(User.id.in_(ids))
    db_users = {u.id: u for u in (await db.execute(stmt)).scalars().all()}

    return [
        PresenceResponse(
            user_id=uid,
            is_online=presence_map.get(uid, False),
            last_seen_at=db_users[uid].last_seen_at if uid in db_users else None,
        )
        for uid in ids
    ]
