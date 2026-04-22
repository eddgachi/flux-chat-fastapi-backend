"""
Message-level operations: edit, delete, read receipts, search, cursor pagination.

All endpoints are scoped under /chats/{chat_id}/messages to keep the URL hierarchy
consistent with the existing chat router.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.connection_manager import manager
from app.core.dependencies import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.message_schema import (
    CursorMessageListResponse,
    MessageReadResponse,
    MessageResponse,
    MessageUpdate,
    UnreadCountResponse,
)
from app.services import chat_service, message_service

router = APIRouter(prefix="/chats", tags=["messages"])


async def _assert_participant(db: AsyncSession, chat_id: int, user_id: int) -> None:
    if not await chat_service.is_participant(db, chat_id, user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


async def _assert_chat_exists(db: AsyncSession, chat_id: int) -> None:
    if not await chat_service.get_chat_by_id(db, chat_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")


# ---------------------------------------------------------------------------
# Cursor-based message history
# ---------------------------------------------------------------------------

@router.get("/{chat_id}/messages/history", response_model=CursorMessageListResponse)
async def get_message_history(
    chat_id: int,
    before: Optional[int] = Query(None, description="Fetch messages older than this message_id"),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Cursor-based pagination for message history.

    Use `before=<message_id>` to load messages older than that ID.
    On first load omit `before`; subsequent pages use `next_cursor` from the response.
    """
    await _assert_participant(db, chat_id, current_user.id)
    await _assert_chat_exists(db, chat_id)

    if before is None:
        # First page: newest messages
        msgs, total = await message_service.get_chat_messages(db, chat_id, skip=0, limit=limit)
        has_more = total > limit
        next_cursor = msgs[0].id if (has_more and msgs) else None
    else:
        msgs, has_more = await message_service.get_messages_before(db, chat_id, before, limit)
        next_cursor = msgs[0].id if (has_more and msgs) else None

    return CursorMessageListResponse(messages=msgs, next_cursor=next_cursor, has_more=has_more)


# ---------------------------------------------------------------------------
# Message search
# ---------------------------------------------------------------------------

@router.get("/{chat_id}/messages/search", response_model=list[MessageResponse])
async def search_messages(
    chat_id: int,
    q: str = Query(..., min_length=1, max_length=200, description="Search keyword"),
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Full-text search within a chat (case-insensitive ILIKE)."""
    await _assert_participant(db, chat_id, current_user.id)
    await _assert_chat_exists(db, chat_id)
    return await message_service.search_messages(db, chat_id, q, limit)


# ---------------------------------------------------------------------------
# Unread count
# ---------------------------------------------------------------------------

@router.get("/{chat_id}/unread", response_model=UnreadCountResponse)
async def get_unread_count(
    chat_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Number of messages the current user hasn't read in this chat."""
    await _assert_participant(db, chat_id, current_user.id)
    count = await message_service.get_unread_count(db, chat_id, current_user.id)
    return UnreadCountResponse(chat_id=chat_id, unread_count=count)


# ---------------------------------------------------------------------------
# Edit message
# ---------------------------------------------------------------------------

@router.patch("/{chat_id}/messages/{message_id}", response_model=MessageResponse)
async def edit_message(
    chat_id: int,
    message_id: int,
    body: MessageUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Edit the content of your own message."""
    await _assert_participant(db, chat_id, current_user.id)

    msg = await message_service.get_message_by_id(db, message_id)
    if not msg or msg.chat_id != chat_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    if msg.sender_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot edit another user's message")
    if msg.is_deleted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot edit a deleted message")

    updated = await message_service.edit_message(db, msg, body.content)

    # Broadcast edit event to all chat participants via Redis
    await manager.publish_to_redis(
        chat_id,
        {
            "type": "message_updated",
            "data": {
                "id": updated.id,
                "chat_id": updated.chat_id,
                "content": updated.content,
                "edited_at": updated.edited_at.isoformat() if updated.edited_at else None,
            },
        },
    )
    return updated


# ---------------------------------------------------------------------------
# Delete message (soft)
# ---------------------------------------------------------------------------

@router.delete("/{chat_id}/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message(
    chat_id: int,
    message_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete your own message. The message slot is retained but content is cleared."""
    await _assert_participant(db, chat_id, current_user.id)

    msg = await message_service.get_message_by_id(db, message_id)
    if not msg or msg.chat_id != chat_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    if msg.sender_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot delete another user's message")
    if msg.is_deleted:
        return  # idempotent

    await message_service.soft_delete_message(db, msg)

    # Notify other participants that the message was deleted
    await manager.publish_to_redis(
        chat_id,
        {
            "type": "message_deleted",
            "data": {"id": message_id, "chat_id": chat_id},
        },
    )


# ---------------------------------------------------------------------------
# Read receipt
# ---------------------------------------------------------------------------

@router.post(
    "/{chat_id}/messages/{message_id}/read",
    response_model=MessageReadResponse,
    status_code=status.HTTP_200_OK,
)
async def mark_message_read(
    chat_id: int,
    message_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Mark a message as read by the current user.
    Idempotent — safe to call multiple times.
    Broadcasts a read_receipt event to all chat participants.
    """
    await _assert_participant(db, chat_id, current_user.id)

    msg = await message_service.get_message_by_id(db, message_id)
    if not msg or msg.chat_id != chat_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    receipt = await message_service.mark_message_read(db, message_id, current_user.id)

    # Broadcast so sender and others can update their read-state UI
    await manager.publish_to_redis(
        chat_id,
        {
            "type": "read_receipt",
            "data": {
                "message_id": message_id,
                "user_id": current_user.id,
                "read_at": receipt.read_at.isoformat(),
            },
        },
    )
    return MessageReadResponse(
        message_id=receipt.message_id,
        user_id=receipt.user_id,
        read_at=receipt.read_at,
    )
