from typing import List, Optional, Tuple

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.chat import Chat
from app.db.models.chat_participant import ChatParticipant


async def get_chat_by_id(db: AsyncSession, chat_id: int) -> Optional[Chat]:
    """Get chat by ID."""
    result = await db.execute(select(Chat).where(Chat.id == chat_id))
    return result.scalar_one_or_none()


async def get_user_chats(
    db: AsyncSession, user_id: int, skip: int = 0, limit: int = 50
) -> Tuple[List[Chat], int]:
    """Get all chats for a user with latest message preview."""
    # Get chat IDs where user is participant
    participant_subquery = (
        select(ChatParticipant.chat_id)
        .where(ChatParticipant.user_id == user_id)
        .subquery()
    )

    # Main query for chats with eager loading of participants
    query = (
        select(Chat)
        .options(selectinload(Chat.participants))
        .where(Chat.id.in_(select(participant_subquery.c.chat_id)))
        .order_by(desc(Chat.updated_at))
        .offset(skip)
        .limit(limit)
    )

    result = await db.execute(query)
    chats = result.scalars().all()

    # Get total count
    count_query = select(func.count()).select_from(participant_subquery)
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    return chats, total


async def create_chat(
    db: AsyncSession, title: Optional[str], is_group: bool, participant_ids: List[int]
) -> Chat:
    """Create a new chat with participants."""
    # Create chat
    chat = Chat(title=title, is_group=is_group)
    db.add(chat)
    await db.flush()  # Get chat.id without committing

    # Add participants
    for user_id in participant_ids:
        participant = ChatParticipant(chat_id=chat.id, user_id=user_id)
        db.add(participant)

    await db.commit()
    await db.refresh(chat)
    return chat


async def add_participant(
    db: AsyncSession, chat_id: int, user_id: int
) -> ChatParticipant:
    """Add a user to an existing chat."""
    participant = ChatParticipant(chat_id=chat_id, user_id=user_id)
    db.add(participant)
    await db.commit()
    await db.refresh(participant)
    return participant


async def remove_participant(db: AsyncSession, chat_id: int, user_id: int) -> bool:
    """Remove a user from a chat."""
    result = await db.execute(
        select(ChatParticipant).where(
            and_(ChatParticipant.chat_id == chat_id, ChatParticipant.user_id == user_id)
        )
    )
    participant = result.scalar_one_or_none()

    if participant:
        await db.delete(participant)
        await db.commit()
        return True
    return False


async def is_participant(db: AsyncSession, chat_id: int, user_id: int) -> bool:
    """Check if a user is a participant in a chat."""
    result = await db.execute(
        select(ChatParticipant).where(
            and_(ChatParticipant.chat_id == chat_id, ChatParticipant.user_id == user_id)
        )
    )
    return result.scalar_one_or_none() is not None


async def get_or_create_private_chat(
    db: AsyncSession, user1_id: int, user2_id: int
) -> Chat:
    """Get existing 1-to-1 chat between two users or create a new one."""
    # Find existing private chat (is_group=False) with exactly these two participants
    # Subquery to find chat IDs where both users are participants
    subquery = (
        select(ChatParticipant.chat_id)
        .where(ChatParticipant.user_id.in_([user1_id, user2_id]))
        .group_by(ChatParticipant.chat_id)
        .having(func.count(ChatParticipant.user_id) == 2)
        .subquery()
    )

    result = await db.execute(
        select(Chat)
        .where(and_(Chat.id.in_(select(subquery.c.chat_id)), Chat.is_group.is_(False)))
        .limit(1)
    )
    chat = result.scalar_one_or_none()

    if chat:
        return chat

    # Create new private chat
    return await create_chat(
        db, title=None, is_group=False, participant_ids=[user1_id, user2_id]
    )


async def get_chat_with_participants(db: AsyncSession, chat_id: int) -> Optional[Chat]:
    """Get chat with participants loaded."""
    result = await db.execute(select(Chat).where(Chat.id == chat_id))
    chat = result.scalar_one_or_none()

    if chat:
        # Load participants relationship
        await db.refresh(chat, attribute_names=["participants"])

    return chat
