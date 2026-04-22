from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import desc, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.message import Message
from app.db.models.message_read import MessageRead


async def create_message(
    db: AsyncSession, chat_id: int, sender_id: int, content: str
) -> Message:
    message = Message(chat_id=chat_id, sender_id=sender_id, content=content)
    db.add(message)

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
    query = (
        select(Message)
        .where(Message.chat_id == chat_id, Message.is_deleted.is_(False))
        .order_by(desc(Message.sent_at))
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(query)
    messages = list(reversed(result.scalars().all()))

    count_query = (
        select(func.count())
        .select_from(Message)
        .where(Message.chat_id == chat_id, Message.is_deleted.is_(False))
    )
    total = (await db.execute(count_query)).scalar_one()

    return messages, total


async def get_messages_before(
    db: AsyncSession, chat_id: int, before_id: int, limit: int = 50
) -> Tuple[List[Message], bool]:
    """Cursor-based pagination: fetch `limit+1` to determine if more pages exist."""
    query = (
        select(Message)
        .where(
            Message.chat_id == chat_id,
            Message.is_deleted.is_(False),
            Message.id < before_id,
        )
        .order_by(desc(Message.id))
        .limit(limit + 1)
    )
    result = await db.execute(query)
    rows = result.scalars().all()

    has_more = len(rows) > limit
    messages = list(reversed(rows[:limit]))
    return messages, has_more


async def get_last_message(db: AsyncSession, chat_id: int) -> Optional[Message]:
    query = (
        select(Message)
        .where(Message.chat_id == chat_id, Message.is_deleted.is_(False))
        .order_by(desc(Message.sent_at))
        .limit(1)
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_message_by_id(db: AsyncSession, message_id: int) -> Optional[Message]:
    result = await db.execute(select(Message).where(Message.id == message_id))
    return result.scalar_one_or_none()


async def edit_message(
    db: AsyncSession, message: Message, new_content: str
) -> Message:
    message.content = new_content
    message.edited_at = datetime.utcnow()
    await db.commit()
    await db.refresh(message)
    return message


async def soft_delete_message(db: AsyncSession, message: Message) -> Message:
    message.is_deleted = True
    message.content = ""
    await db.commit()
    await db.refresh(message)
    return message


async def mark_message_read(
    db: AsyncSession, message_id: int, user_id: int
) -> MessageRead:
    """Upsert a read receipt (idempotent)."""
    stmt = (
        pg_insert(MessageRead)
        .values(message_id=message_id, user_id=user_id, read_at=datetime.utcnow())
        .on_conflict_do_nothing(constraint="uq_message_read")
        .returning(MessageRead)
    )
    result = await db.execute(stmt)
    await db.commit()

    row = result.scalar_one_or_none()
    if row is None:
        existing = await db.execute(
            select(MessageRead).where(
                MessageRead.message_id == message_id,
                MessageRead.user_id == user_id,
            )
        )
        row = existing.scalar_one()
    return row


async def get_unread_count(db: AsyncSession, chat_id: int, user_id: int) -> int:
    """Count messages in a chat the user hasn't read yet."""
    read_subquery = (
        select(MessageRead.message_id)
        .where(MessageRead.user_id == user_id)
        .subquery()
    )
    query = (
        select(func.count())
        .select_from(Message)
        .where(
            Message.chat_id == chat_id,
            Message.is_deleted.is_(False),
            Message.sender_id != user_id,
            Message.id.not_in(select(read_subquery.c.message_id)),
        )
    )
    return (await db.execute(query)).scalar_one()


async def search_messages(
    db: AsyncSession, chat_id: int, query: str, limit: int = 20
) -> List[Message]:
    """Case-insensitive full-text search within a chat."""
    stmt = (
        select(Message)
        .where(
            Message.chat_id == chat_id,
            Message.is_deleted.is_(False),
            or_(Message.content.ilike(f"%{query}%")),
        )
        .order_by(desc(Message.sent_at))
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()
