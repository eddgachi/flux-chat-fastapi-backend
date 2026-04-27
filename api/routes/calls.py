import secrets
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user
from db.models.call import Call
from db.models.user import User
from db.session import get_db
from schemas.call import CallHistoryOut

router = APIRouter(prefix="/calls", tags=["calls"])


@router.get("/turn-credentials")
async def get_turn_credentials(current_user: User = Depends(get_current_user)):
    """
    Returns temporary TURN credentials for WebRTC.
    In production, integrate with Coturn's `turnserver` with REST API.
    For development, return a dummy that works with a public STUN only.
    """
    return {
        "ttl": 86400,
        "username": f"{current_user.id}:{int(datetime.utcnow().timestamp())}",
        "password": secrets.token_urlsafe(16),
        "urls": [
            "stun:stun.l.google.com:19302",
        ],
    }


@router.get("/history", response_model=List[CallHistoryOut])
async def get_call_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
):
    """Get call history for the current user (both initiated and received calls)."""
    stmt = (
        select(Call)
        .where(
            or_(
                Call.initiator_id == current_user.id,
                Call.receiver_id == current_user.id,
            )
        )
        .order_by(Call.started_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    calls = result.scalars().all()
    return [CallHistoryOut.model_validate(call) for call in calls]
