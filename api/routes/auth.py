import os
import random
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.user import User, UserSession
from db.session import get_db
from schemas.auth import OTPRequest, OTPVerify, RefreshRequest, TokenResponse
from utils.security import create_access_token, create_refresh_token, decode_token

router = APIRouter(prefix="/auth", tags=["auth"])

# Development mock OTP – always accept this code if set
MOCK_OTP = os.getenv("MOCK_OTP", "123456")

# In production: store OTP in Redis with TTL. For simplicity here we keep in memory (not scalable).
# Since we have Redis already, we'll use it.
import redis.asyncio as redis

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
redis_client = None


async def get_redis():
    global redis_client
    if redis_client is None:
        redis_client = await redis.from_url(REDIS_URL, decode_responses=True)
    return redis_client


@router.post("/request-otp")
async def request_otp(data: OTPRequest, db: AsyncSession = Depends(get_db)):
    """Send a 6-digit OTP to the given phone number. In dev, prints to console."""
    # Check if user exists, if not we'll create later during verification.
    code = str(random.randint(100000, 999999))
    # Store code in Redis with phone number as key, expire in 5 minutes
    r = await get_redis()
    await r.setex(f"otp:{data.phone_number}", 300, code)

    # In real system: send via Twilio. For dev, just print.
    print(f"\n🔐 OTP for {data.phone_number}: {code}\n")
    return {"message": "OTP sent (check console)"}


@router.post("/verify-otp", response_model=TokenResponse)
async def verify_otp(data: OTPVerify, db: AsyncSession = Depends(get_db)):
    r = await get_redis()
    stored_code = await r.get(f"otp:{data.phone_number}")
    if not stored_code or (data.code != stored_code and data.code != MOCK_OTP):
        raise HTTPException(status_code=400, detail="Invalid OTP")

    # Delete used OTP
    await r.delete(f"otp:{data.phone_number}")

    # Find or create user
    result = await db.execute(
        select(User).where(User.phone_number == data.phone_number)
    )
    user = result.scalar_one_or_none()
    if not user:
        user = User(phone_number=data.phone_number)
        db.add(user)
        await db.commit()
        await db.refresh(user)

    # Create tokens
    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    # Store refresh token in DB
    expires_at = datetime.utcnow() + timedelta(days=7)
    user_session = UserSession(
        user_id=user.id, refresh_token=refresh_token, expires_at=expires_at
    )
    db.add(user_session)
    await db.commit()

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_token(data.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    # Check if refresh token exists and not expired
    result = await db.execute(
        select(UserSession).where(
            UserSession.refresh_token == data.refresh_token,
            UserSession.expires_at > datetime.utcnow(),
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=401, detail="Refresh token invalid or expired")

    # Rotate refresh token (optional but recommended)
    new_access = create_access_token(data={"sub": user_id})
    new_refresh = create_refresh_token(data={"sub": user_id})
    new_expires = datetime.utcnow() + timedelta(days=7)

    # Update the existing session with new refresh token
    session.refresh_token = new_refresh
    session.expires_at = new_expires
    await db.commit()

    return TokenResponse(access_token=new_access, refresh_token=new_refresh)
