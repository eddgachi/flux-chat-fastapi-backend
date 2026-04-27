from datetime import datetime, timedelta, timezone
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user
from db.models.media import Media
from db.models.status import Status, StatusView
from db.models.user import User
from db.session import get_db
from schemas.status import StatusCreate, StatusOut, StatusViewerOut
from utils.privacy import can_view_status

router = APIRouter(prefix="/status", tags=["status"])


@router.post("/", response_model=dict)
async def create_status(
    data: StatusCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Validate: either text or media_id provided
    if not data.text and not data.media_id:
        raise HTTPException(status_code=400, detail="Either text or media_id required")
    if data.media_id:
        media = await db.get(Media, data.media_id)
        if not media or media.user_id != current_user.id:
            raise HTTPException(status_code=400, detail="Invalid media_id")
    # Set expiry 24h from now
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    status = Status(
        user_id=current_user.id,
        media_id=data.media_id,
        text=data.text,
        privacy=data.privacy,
        expires_at=expires_at,
    )
    db.add(status)
    await db.commit()
    return {"status_id": str(status.id), "expires_at": expires_at.isoformat()}


@router.get("/", response_model=List[StatusOut])
async def get_statuses(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Get all statuses that are not expired and belong to users that current_user can view
    now = datetime.now(timezone.utc)
    # Subquery: get statuses with their authors, filter by expiry
    stmt = (
        select(Status, User)
        .join(User, Status.user_id == User.id)
        .where(Status.expires_at > now)
        .order_by(Status.created_at.desc())
    )
    result = await db.execute(stmt)
    rows = result.all()

    # Collect which statuses the current user has already viewed
    viewed_status_ids = set()
    if rows:
        status_ids = [row[0].id for row in rows]
        view_stmt = select(StatusView.status_id).where(
            StatusView.status_id.in_(status_ids),
            StatusView.viewer_id == current_user.id,
        )
        view_res = await db.execute(view_stmt)
        viewed_status_ids = {row[0] for row in view_res.all()}

    # Filter by privacy and blocks
    statuses_out = []
    for _status, user in rows:
        if not await can_view_status(db, _status, current_user.id):
            continue
        # Build media URLs
        media_url = None
        thumbnail_url = None
        if _status.media_id:
            media_url = f"/media/{_status.media_id}"
            # We'll assume if thumbnail exists, it's at /media/{media_id}?thumbnail=true
            thumbnail_url = f"/media/{_status.media_id}?thumbnail=true"
        statuses_out.append(
            StatusOut(
                id=_status.id,
                user_id=user.id,
                user_name=user.name or user.phone_number,
                user_avatar=user.avatar_url,
                text=_status.text,
                media_id=_status.media_id,
                media_url=media_url,
                thumbnail_url=thumbnail_url,
                created_at=_status.created_at,
                expires_at=_status.expires_at,
                viewed=(_status.id in viewed_status_ids),
            )
        )
    return statuses_out


@router.post("/{status_id}/view", status_code=status.HTTP_204_NO_CONTENT)
async def view_status(
    status_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    status = await db.get(Status, status_id)
    if not status or status.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=404, detail="Status not found")
    # Check if user can view
    if not await can_view_status(db, status, current_user.id):
        raise HTTPException(status_code=403, detail="Not allowed to view this status")
    # Record view if not already
    existing = await db.execute(
        select(StatusView).where(
            StatusView.status_id == status_id, StatusView.viewer_id == current_user.id
        )
    )
    if not existing.scalar_one_or_none():
        view = StatusView(status_id=status_id, viewer_id=current_user.id)
        db.add(view)
        await db.commit()


@router.get("/{status_id}/views", response_model=List[StatusViewerOut])
async def get_status_views(
    status_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    status = await db.get(Status, status_id)
    if not status:
        raise HTTPException(status_code=404, detail="Status not found")
    # Only author can see viewers
    if status.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    stmt = (
        select(StatusView, User)
        .join(User, StatusView.viewer_id == User.id)
        .where(StatusView.status_id == status_id)
        .order_by(StatusView.viewed_at.desc())
    )
    result = await db.execute(stmt)
    rows = result.all()
    return [
        StatusViewerOut(
            viewer_id=row[1].id,
            viewer_name=row[1].name or row[1].phone_number,
            viewer_avatar=row[1].avatar_url,
            viewed_at=row[0].viewed_at,
        )
        for row in rows
    ]
