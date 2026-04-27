from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user
from db.models.chat import Chat, ChatParticipant, ChatType
from db.models.message import Message
from db.models.user import User
from db.session import get_db
from schemas.chat import ChatOut
from schemas.message import MessageOut

router = APIRouter(prefix="/chats", tags=["chats"])


@router.post("/private/{other_user_id}", response_model=ChatOut)
async def create_or_get_private_chat(
    other_user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Check that other user exists
    other_user = await db.get(User, other_user_id)
    if not other_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Find existing private chat between these two users
    # A private chat has exactly two participants: current_user and other_user
    stmt = (
        select(Chat)
        .join(ChatParticipant, Chat.id == ChatParticipant.chat_id)
        .where(Chat.type == ChatType.PRIVATE)
        .group_by(Chat.id)
        .having(func.count(ChatParticipant.user_id) == 2)
        .having(
            and_(
                func.bool_or(ChatParticipant.user_id == current_user.id),
                func.bool_or(ChatParticipant.user_id == other_user_id),
            )
        )
    )
    result = await db.execute(stmt)
    chat = result.scalar_one_or_none()

    if not chat:
        # Create new private chat
        chat = Chat(type=ChatType.PRIVATE)
        db.add(chat)
        await db.flush()
        # Add participants
        participants = [
            ChatParticipant(chat_id=chat.id, user_id=current_user.id),
            ChatParticipant(chat_id=chat.id, user_id=other_user_id),
        ]
        db.add_all(participants)
        await db.commit()
        await db.refresh(chat)

    return chat


@router.get("/", response_model=List[ChatOut])
async def list_chats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Get all chats where current_user is a participant, ordered by latest message time (optional)
    stmt = (
        select(Chat)
        .join(ChatParticipant, Chat.id == ChatParticipant.chat_id)
        .where(ChatParticipant.user_id == current_user.id)
        .order_by(Chat.created_at.desc())  # better: order by last_message_time
    )
    result = await db.execute(stmt)
    chats = result.scalars().all()
    return chats


@router.get("/{chat_id}/messages", response_model=List[MessageOut])
async def get_messages(
    chat_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    before: Optional[datetime] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify user is participant in this chat
    participant_check = await db.execute(
        select(ChatParticipant).where(
            ChatParticipant.chat_id == chat_id,
            ChatParticipant.user_id == current_user.id,
        )
    )
    if not participant_check.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Not a participant")

    query = select(Message).where(Message.chat_id == chat_id)
    if before:
        query = query.where(Message.created_at < before)
    query = query.order_by(desc(Message.created_at)).limit(limit)
    result = await db.execute(query)
    messages = result.scalars().all()
    # Return in chronological order (oldest first) for convenience
    return list(reversed(messages))
