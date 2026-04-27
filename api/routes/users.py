from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user
from db.models.user import User
from db.session import get_db
from schemas.user import UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=UserOut)
async def update_me(
    update: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if update.name is not None:
        current_user.name = update.name
    if update.avatar_url is not None:
        current_user.avatar_url = update.avatar_url
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.get("/{user_id}/presence")
async def get_user_presence(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Check if target user exists
    target = await db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    from utils.presence import is_online

    online = await is_online(user_id)
    if online:
        return {"user_id": user_id, "status": "online", "last_seen": None}
    else:
        # last_seen is stored in DB
        return {
            "user_id": user_id,
            "status": "offline",
            "last_seen": target.last_seen.isoformat() if target.last_seen else None,
        }
