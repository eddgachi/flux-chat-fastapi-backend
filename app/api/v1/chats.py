from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.chat_schema import AddParticipantRequest, ChatCreate, ChatResponse
from app.schemas.message_schema import MessageListResponse
from app.services import chat_service, message_service

router = APIRouter(prefix="/chats", tags=["chats"])


@router.post("/", response_model=ChatResponse, status_code=status.HTTP_201_CREATED)
async def create_chat(
    chat_data: ChatCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new chat (1-to-1 or group).

    - For 1-to-1 chats: provide the other user's ID in `participant_ids`.
    - For group chats: provide all participant IDs (excluding yourself).
    The current user is automatically added as a participant.
    """
    if not chat_data.participant_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one other participant is required",
        )

    # Build full participant list (including current user)
    all_participant_ids = list(set([current_user.id] + chat_data.participant_ids))

    # For 1-to-1 chats, get or create the private chat
    if not chat_data.is_group:
        if len(all_participant_ids) != 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="1-to-1 chats must have exactly 2 participants (you + 1 other)",
            )
        other_user_id = [uid for uid in all_participant_ids if uid != current_user.id][
            0
        ]
        chat = await chat_service.get_or_create_private_chat(
            db, current_user.id, other_user_id
        )
    else:
        # Create group chat
        chat = await chat_service.create_chat(
            db,
            title=chat_data.title,
            is_group=True,
            participant_ids=all_participant_ids,
        )

    # Load participants for response
    chat = await chat_service.get_chat_with_participants(db, chat.id)

    return chat


@router.get("/", response_model=List[ChatResponse])
async def list_chats(
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all chats for the current user."""
    chats, total = await chat_service.get_user_chats(db, current_user.id, skip, limit)

    # Enrich with last message preview
    result = []
    for chat in chats:
        last_msg = await message_service.get_last_message(db, chat.id)
        chat_dict = {
            "id": chat.id,
            "title": chat.title,
            "is_group": chat.is_group,
            "created_at": chat.created_at,
            "updated_at": chat.updated_at,
            "participants": chat.participants,
            "last_message_preview": last_msg.content[:50] if last_msg else None,
            "last_message_time": last_msg.sent_at if last_msg else None,
        }
        result.append(ChatResponse(**chat_dict))

    return result


@router.get("/{chat_id}/messages", response_model=MessageListResponse)
async def get_messages(
    chat_id: int,
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get messages for a specific chat."""
    # Check if user is participant
    is_participant = await chat_service.is_participant(db, chat_id, current_user.id)
    if not is_participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this chat"
        )

    # Check if chat exists
    chat = await chat_service.get_chat_by_id(db, chat_id)
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found"
        )

    # Get messages
    messages, total = await message_service.get_chat_messages(db, chat_id, skip, limit)

    return MessageListResponse(messages=messages, total=total, skip=skip, limit=limit)


@router.post("/{chat_id}/participants", status_code=status.HTTP_201_CREATED)
async def add_participant(
    chat_id: int,
    request: AddParticipantRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a user to an existing chat."""
    # Check if current user is participant
    is_participant = await chat_service.is_participant(db, chat_id, current_user.id)
    if not is_participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only chat participants can add new members",
        )

    # Check if user already in chat
    already_participant = await chat_service.is_participant(
        db, chat_id, request.user_id
    )
    if already_participant:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already a participant",
        )

    # Add participant
    await chat_service.add_participant(db, chat_id, request.user_id)

    return {"message": "Participant added successfully"}


@router.delete("/{chat_id}/participants/{user_id}")
async def remove_participant(
    chat_id: int,
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a user from a chat."""
    # Check if current user is participant
    is_participant = await chat_service.is_participant(db, chat_id, current_user.id)
    if not is_participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only chat participants can remove members",
        )

    # Cannot remove self if last participant? (simplify for now)
    success = await chat_service.remove_participant(db, chat_id, user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Participant not found"
        )

    return {"message": "Participant removed successfully"}
