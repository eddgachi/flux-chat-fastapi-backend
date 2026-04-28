import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def collect_user_backup_data(user_id: UUID, db: AsyncSession) -> dict:
    from db.models.chat import Chat, ChatParticipant
    from db.models.message import Message, StarredMessage
    from db.models.user import User

    # Get user info
    user = await db.get(User, user_id)
    if not user:
        raise ValueError("User not found")

    # Get all chats where user participates, with pinned/archived flags
    chats_query = (
        select(
            Chat,
            ChatParticipant.pinned,
            ChatParticipant.archived,
            ChatParticipant.muted_until,
        )
        .join(ChatParticipant, Chat.id == ChatParticipant.chat_id)
        .where(ChatParticipant.user_id == user_id)
    )
    chats_result = await db.execute(chats_query)
    chats_data = []
    for chat, pinned, archived, muted_until in chats_result:
        chats_data.append(
            {
                "id": str(chat.id),
                "type": chat.type,
                "group_name": chat.group_name,
                "group_avatar": chat.group_avatar,
                "created_at": chat.created_at.isoformat(),
                "pinned": pinned,
                "archived": archived,
                "muted_until": muted_until.isoformat() if muted_until else None,
            }
        )

    # Get all messages in those chats
    chat_ids = [chat["id"] for chat in chats_data]
    messages_query = select(Message).where(Message.chat_id.in_(chat_ids))
    messages_result = await db.execute(messages_query)
    messages_data = []
    for msg in messages_result.scalars():
        messages_data.append(
            {
                "id": str(msg.id),
                "chat_id": str(msg.chat_id),
                "sender_id": str(msg.sender_id),
                "text": msg.text,
                "media_id": str(msg.media_id) if msg.media_id else None,
                "status": msg.status.value if msg.status else None,
                "reply_to_id": str(msg.reply_to_id) if msg.reply_to_id else None,
                "created_at": msg.created_at.isoformat(),
            }
        )

    # Get starred messages for this user
    starred_query = select(StarredMessage.message_id).where(
        StarredMessage.user_id == user_id
    )
    starred_result = await db.execute(starred_query)
    starred_message_ids = [str(row[0]) for row in starred_result.all()]

    backup = {
        "metadata": {
            "user_id": str(user.id),
            "phone_number": user.phone_number,
            "export_date": datetime.utcnow().isoformat(),
            "version": "1.0",
            "chat_count": len(chats_data),
            "message_count": len(messages_data),
        },
        "user": {
            "name": user.name,
            "avatar_url": user.avatar_url,
        },
        "chats": chats_data,
        "messages": messages_data,
        "starred_message_ids": starred_message_ids,
    }
    return backup
