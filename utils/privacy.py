from uuid import UUID

from sqlalchemy import func, select

from db.models.chat import Chat, ChatParticipant, ChatType
from db.models.status import Status


async def can_view_status(db, status: Status, viewer_id: UUID) -> bool:
    if status.user_id == viewer_id:
        return True
    # Check blocks: viewer blocked by author? author blocked by viewer?
    # We'll add later. For now, assume no blocks.
    if status.privacy == "my_contacts":
        # Check if there is a private chat between them
        stmt = (
            select(Chat)
            .join(ChatParticipant)
            .where(
                Chat.type == ChatType.PRIVATE,
                ChatParticipant.user_id.in_([status.user_id, viewer_id]),
            )
            .group_by(Chat.id)
            .having(func.count(ChatParticipant.user_id) == 2)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none() is not None
    elif status.privacy == "close_friends":
        # Placeholder – return False for now
        return False
    return False
