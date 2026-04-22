from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash, verify_password
from app.db.models.user import User


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    """Get a user by email."""
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
    """Get a user by username."""
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
    """Get a user by ID."""
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession, username: str, email: str, password: str
) -> User:
    """Create a new user."""
    hashed_password = get_password_hash(password)
    user = User(
        username=username, email=email, hashed_password=hashed_password, is_active=True
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(
    db: AsyncSession, username_or_email: str, password: str
) -> Optional[User]:
    """Authenticate a user by username/email and password."""
    # Try to find by username first, then by email
    user = await get_user_by_username(db, username_or_email)
    if not user:
        user = await get_user_by_email(db, username_or_email)

    if not user:
        return None

    if not verify_password(password, user.hashed_password):
        return None

    return user
