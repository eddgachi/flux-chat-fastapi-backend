from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.message import Message


async def create_message(
    db: AsyncSession, chat_id: int, sender_id: int, content: str
) -> Message:
    """Create a new message."""
    message = Message(chat_id=chat_id, sender_id=sender_id, content=content)
    db.add(message)

    # Update chat's updated_at timestamp
    from app.db.models.chat import Chat

    result = await db.execute(select(Chat).where(Chat.id == chat_id))
    chat = result.scalar_one_or_none()
    if chat:
        chat.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(message)
    return message


async def get_chat_messages(
    db: AsyncSession, chat_id: int, skip: int = 0, limit: int = 50
) -> Tuple[List[Message], int]:
    """Get paginated messages for a chat."""
    # Get messages
    query = (
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(desc(Message.sent_at))
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(query)
    messages = result.scalars().all()

    # Reverse to get chronological order (oldest first)
    messages = list(reversed(messages))

    # Get total count
    count_query = (
        select(func.count()).select_from(Message).where(Message.chat_id == chat_id)
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    return messages, total


async def get_last_message(db: AsyncSession, chat_id: int) -> Optional[Message]:
    """Get the most recent message in a chat."""
    query = (
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(desc(Message.sent_at))
        .limit(1)
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()
