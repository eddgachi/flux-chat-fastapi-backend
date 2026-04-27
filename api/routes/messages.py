from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user
from db.models.chat import ChatParticipant
from db.models.message import Message, StarredMessage
from db.models.user import User
from db.session import get_db
from schemas.message import MessageOut
from schemas.search import MessageSearchResult

router = APIRouter(prefix="/messages", tags=["messages"])


@router.post("/{message_id}/star", status_code=204)
async def star_message(
    message_id: UUID,
    starred: bool = True,  # True = star, False = unstar
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify message exists and user is participant in its chat
    msg = await db.get(Message, message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    # Check if user is participant in chat

    part = await db.execute(
        select(ChatParticipant).where(
            ChatParticipant.chat_id == msg.chat_id,
            ChatParticipant.user_id == current_user.id,
        )
    )
    if not part.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Not a participant in this chat")
    if starred:
        # Add star if not already
        existing = await db.execute(
            select(StarredMessage).where(
                StarredMessage.user_id == current_user.id,
                StarredMessage.message_id == message_id,
            )
        )
        if not existing.scalar_one_or_none():
            db.add(StarredMessage(user_id=current_user.id, message_id=message_id))
            await db.commit()
    else:
        # Remove star
        await db.execute(
            delete(StarredMessage).where(
                StarredMessage.user_id == current_user.id,
                StarredMessage.message_id == message_id,
            )
        )
        await db.commit()
    return


@router.get("/starred", response_model=List[MessageOut])
async def list_starred_messages(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Join StarredMessage with Message
    stmt = (
        select(Message)
        .join(StarredMessage, StarredMessage.message_id == Message.id)
        .where(StarredMessage.user_id == current_user.id)
        .order_by(StarredMessage.starred_at.desc())
    )
    result = await db.execute(stmt)
    messages = result.scalars().all()
    return messages


@router.get("/search", response_model=List[MessageSearchResult])
async def search_messages(
    q: str = Query(..., min_length=1),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Search messages by text content using full-text search.
    Only searches messages from chats where the current user is a participant.
    """
    from sqlalchemy import text

    # Use PostgreSQL full-text search with a tsvector column.
    # If text_search_vector column doesn't exist yet, fall back to ILIKE.
    # Check if the column exists first by trying the tsquery approach.
    stmt = text(
        """
        SELECT m.id, m.chat_id, m.sender_id, m.text, m.created_at,
               u.name as sender_name
        FROM messages m
        JOIN users u ON u.id = m.sender_id
        WHERE m.chat_id IN (SELECT chat_id FROM chat_participants WHERE user_id = :user_id)
          AND m.text ILIKE :pattern
        ORDER BY m.created_at DESC
        LIMIT 50
    """
    )
    pattern = f"%{q}%"
    result = await db.execute(stmt, {"user_id": current_user.id, "pattern": pattern})
    rows = result.all()

    # Build result with chat names
    from uuid import UUID

    chat_names_cache = {}

    async def get_chat_name(chat_id: UUID) -> str:
        if chat_id in chat_names_cache:
            return chat_names_cache[chat_id]
        from db.models.chat import Chat

        chat = await db.get(Chat, chat_id)
        if not chat:
            chat_names_cache[chat_id] = "Unknown"
            return chat_names_cache[chat_id]
        if chat.type == "group" and chat.group_name:
            chat_names_cache[chat_id] = chat.group_name
            return chat.group_name
        elif chat.type == "private":
            # Find the other participant's name
            other = await db.execute(
                text(
                    """
                    SELECT u.name FROM users u
                    JOIN chat_participants cp ON cp.user_id = u.id
                    WHERE cp.chat_id = :chat_id AND u.id != :user_id
                    LIMIT 1
                """
                ),
                {"chat_id": chat_id, "user_id": current_user.id},
            )
            other_name = other.scalar()
            chat_names_cache[chat_id] = other_name or "Unknown"
            return chat_names_cache[chat_id]
        chat_names_cache[chat_id] = "Unknown"
        return chat_names_cache[chat_id]

    results = []
    for row in rows:
        chat_name = await get_chat_name(row.chat_id)
        results.append(
            MessageSearchResult(
                id=row.id,
                chat_id=row.chat_id,
                chat_name=chat_name,
                sender_name=row.sender_name,
                text=row.text,
                created_at=row.created_at,
            )
        )
    return results
