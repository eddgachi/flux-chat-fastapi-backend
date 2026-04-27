from datetime import datetime, timezone
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
    include_archived: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Build query for ChatParticipant with pinned/archived, join Chat, left join last message
    # We'll do a subquery for last message per chat
    last_msg_subq = (
        select(Message.chat_id, func.max(Message.created_at).label("last_msg_time"))
        .group_by(Message.chat_id)
        .subquery()
    )
    stmt = (
        select(
            Chat,
            ChatParticipant.pinned,
            ChatParticipant.archived,
            last_msg_subq.c.last_msg_time,
        )
        .join(ChatParticipant, Chat.id == ChatParticipant.chat_id)
        .outerjoin(last_msg_subq, Chat.id == last_msg_subq.c.chat_id)
        .where(ChatParticipant.user_id == current_user.id)
    )
    if not include_archived:
        stmt = stmt.where(ChatParticipant.archived == False)
    # Order by pinned DESC, then last_msg_time DESC (NULLs last)
    stmt = stmt.order_by(
        ChatParticipant.pinned.desc(), last_msg_subq.c.last_msg_time.desc().nullslast()
    )
    result = await db.execute(stmt)
    rows = result.all()
    chats = []
    for row in rows:
        chat = row[0]
        # We'll convert to ChatOut – but we need to include pinned/archived flags? Maybe extend schema.
        # For simplicity, we can return a separate DTO that includes flags.
        # We'll modify ChatOut to have optional pinned/archived fields.
        chats.append(chat)
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


@router.patch("/{chat_id}/pin")
async def pin_chat(
    chat_id: UUID,
    pinned: bool = True,  # query param or body? Use query param for simplicity
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify user is participant
    cp = await db.execute(
        select(ChatParticipant).where(
            ChatParticipant.chat_id == chat_id,
            ChatParticipant.user_id == current_user.id,
        )
    )
    cp = cp.scalar_one_or_none()
    if not cp:
        raise HTTPException(status_code=403, detail="Not a participant")
    cp.pinned = pinned
    await db.commit()
    # Notify via WebSocket (if user connected)
    from services.websocket_manager import manager

    await manager.send_personal_message(
        current_user.id,
        {"type": "chat_list_update", "chat_id": str(chat_id), "pinned": pinned},
    )
    return {"pinned": pinned}


@router.patch("/{chat_id}/archive")
async def archive_chat(
    chat_id: UUID,
    archived: bool = True,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cp = await db.execute(
        select(ChatParticipant).where(
            ChatParticipant.chat_id == chat_id,
            ChatParticipant.user_id == current_user.id,
        )
    )
    cp = cp.scalar_one_or_none()
    if not cp:
        raise HTTPException(status_code=403, detail="Not a participant")
    cp.archived = archived
    await db.commit()
    from services.websocket_manager import manager

    await manager.send_personal_message(
        current_user.id,
        {"type": "chat_list_update", "chat_id": str(chat_id), "archived": archived},
    )
    return {"archived": archived}


@router.patch("/{chat_id}/mute")
async def mute_chat(
    chat_id: UUID,
    until: Optional[datetime] = Query(
        None
    ),  # ISO timestamp, if None -> forever (set far future)
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cp = await db.execute(
        select(ChatParticipant).where(
            ChatParticipant.chat_id == chat_id,
            ChatParticipant.user_id == current_user.id,
        )
    )
    cp = cp.scalar_one_or_none()
    if not cp:
        raise HTTPException(status_code=403, detail="Not a participant")
    if until is None:
        # mute forever (set to year 2100)
        until = datetime(2100, 1, 1, tzinfo=timezone.utc)
    cp.muted_until = until
    await db.commit()
    return {"muted_until": until.isoformat()}


@router.patch("/{chat_id}/unmute")
async def unmute_chat(
    chat_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cp = await db.execute(
        select(ChatParticipant).where(
            ChatParticipant.chat_id == chat_id,
            ChatParticipant.user_id == current_user.id,
        )
    )
    cp = cp.scalar_one_or_none()
    if not cp:
        raise HTTPException(status_code=403, detail="Not a participant")
    cp.muted_until = None
    await db.commit()
    return {"muted": False}
