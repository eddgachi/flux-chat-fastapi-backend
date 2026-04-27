from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user
from db.models.chat import Chat, ChatParticipant, ChatType
from db.models.user import User
from db.session import get_db
from schemas.group import (
    AddParticipant,
    GroupCreate,
    GroupOut,
    GroupUpdate,
    ParticipantOut,
    UpdateRole,
)

router = APIRouter(prefix="/groups", tags=["groups"])


@router.post("/", response_model=GroupOut)
async def create_group(
    group_data: GroupCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Ensure at least one member besides creator
    if current_user.id not in group_data.member_ids:
        group_data.member_ids.append(current_user.id)
    # Validate all member_ids exist
    members = []
    for uid in set(group_data.member_ids):
        user = await db.get(User, uid)
        if not user:
            raise HTTPException(status_code=404, detail=f"User {uid} not found")
        members.append(user)

    # Create chat of type group
    chat = Chat(
        type=ChatType.GROUP,
        group_name=group_data.name,
        group_avatar=group_data.avatar_url,
    )
    db.add(chat)
    await db.flush()

    # Add participants, creator as admin
    participants = []
    for user in members:
        role = "admin" if user.id == current_user.id else "member"
        participants.append(
            ChatParticipant(
                chat_id=chat.id,
                user_id=user.id,
                role=role,
            )
        )
    db.add_all(participants)
    await db.commit()
    await db.refresh(chat)

    return GroupOut(
        id=chat.id,
        name=chat.group_name,
        avatar_url=chat.group_avatar,
        created_at=chat.created_at,
        participants_count=len(members),
    )


@router.get("/{group_id}", response_model=GroupOut)
async def get_group(
    group_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Check user is participant
    chat = await db.get(Chat, group_id)
    if not chat or chat.type != ChatType.GROUP:
        raise HTTPException(status_code=404, detail="Group not found")
    participant = await db.execute(
        select(ChatParticipant).where(
            ChatParticipant.chat_id == group_id,
            ChatParticipant.user_id == current_user.id,
        )
    )
    if not participant.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Not a member")
    # Count participants
    count_result = await db.execute(
        select(func.count())
        .select_from(ChatParticipant)
        .where(ChatParticipant.chat_id == group_id)
    )
    count = count_result.scalar()
    return GroupOut(
        id=chat.id,
        name=chat.group_name,
        avatar_url=chat.group_avatar,
        created_at=chat.created_at,
        participants_count=count,
    )


@router.patch("/{group_id}", response_model=GroupOut)
async def update_group(
    group_id: UUID,
    update: GroupUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    chat = await db.get(Chat, group_id)
    if not chat or chat.type != ChatType.GROUP:
        raise HTTPException(status_code=404, detail="Group not found")
    # Check admin
    participant = await db.execute(
        select(ChatParticipant).where(
            ChatParticipant.chat_id == group_id,
            ChatParticipant.user_id == current_user.id,
            ChatParticipant.role == "admin",
        )
    )
    if not participant.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Admin required")
    if update.name is not None:
        chat.group_name = update.name
    if update.avatar_url is not None:
        chat.group_avatar = update.avatar_url
    await db.commit()
    await db.refresh(chat)
    # recount participants
    count_result = await db.execute(
        select(func.count())
        .select_from(ChatParticipant)
        .where(ChatParticipant.chat_id == group_id)
    )
    count = count_result.scalar()
    return GroupOut(
        id=chat.id,
        name=chat.group_name,
        avatar_url=chat.group_avatar,
        created_at=chat.created_at,
        participants_count=count,
    )


@router.post("/{group_id}/participants", status_code=status.HTTP_204_NO_CONTENT)
async def add_participant(
    group_id: UUID,
    data: AddParticipant,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Admin check
    admin_check = await db.execute(
        select(ChatParticipant).where(
            ChatParticipant.chat_id == group_id,
            ChatParticipant.user_id == current_user.id,
            ChatParticipant.role == "admin",
        )
    )
    if not admin_check.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Admin required")
    # Check group exists
    chat = await db.get(Chat, group_id)
    if not chat or chat.type != ChatType.GROUP:
        raise HTTPException(status_code=404, detail="Group not found")
    # Check user to add exists
    user_to_add = await db.get(User, data.user_id)
    if not user_to_add:
        raise HTTPException(status_code=404, detail="User not found")
    # Check not already a participant
    existing = await db.execute(
        select(ChatParticipant).where(
            ChatParticipant.chat_id == group_id, ChatParticipant.user_id == data.user_id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Already a member")
    # Add
    new_participant = ChatParticipant(
        chat_id=group_id, user_id=data.user_id, role="member"
    )
    db.add(new_participant)
    await db.commit()


@router.delete(
    "/{group_id}/participants/{user_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_participant(
    group_id: UUID,
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Check group
    chat = await db.get(Chat, group_id)
    if not chat or chat.type != ChatType.GROUP:
        raise HTTPException(status_code=404, detail="Group not found")
    # Permission: admin or self-removal
    is_admin = await db.execute(
        select(ChatParticipant).where(
            ChatParticipant.chat_id == group_id,
            ChatParticipant.user_id == current_user.id,
            ChatParticipant.role == "admin",
        )
    )
    is_self = current_user.id == user_id
    if not (is_admin.scalar_one_or_none() or is_self):
        raise HTTPException(status_code=403, detail="Not allowed")
    # Cannot remove last admin? We'll allow but keep at least one admin? We'll not enforce for simplicity.
    participant = await db.execute(
        select(ChatParticipant).where(
            ChatParticipant.chat_id == group_id, ChatParticipant.user_id == user_id
        )
    )
    participant = participant.scalar_one_or_none()
    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")
    await db.delete(participant)
    await db.commit()


@router.patch(
    "/{group_id}/participants/{user_id}/role", status_code=status.HTTP_204_NO_CONTENT
)
async def change_role(
    group_id: UUID,
    user_id: UUID,
    role_data: UpdateRole,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Only admin can change roles
    admin_check = await db.execute(
        select(ChatParticipant).where(
            ChatParticipant.chat_id == group_id,
            ChatParticipant.user_id == current_user.id,
            ChatParticipant.role == "admin",
        )
    )
    if not admin_check.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Admin required")
    if role_data.role not in ["admin", "member"]:
        raise HTTPException(status_code=400, detail="Invalid role")
    participant = await db.execute(
        select(ChatParticipant).where(
            ChatParticipant.chat_id == group_id, ChatParticipant.user_id == user_id
        )
    )
    participant = participant.scalar_one_or_none()
    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")
    participant.role = role_data.role
    await db.commit()


@router.get("/{group_id}/participants", response_model=List[ParticipantOut])
async def list_participants(
    group_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Check membership
    check = await db.execute(
        select(ChatParticipant).where(
            ChatParticipant.chat_id == group_id,
            ChatParticipant.user_id == current_user.id,
        )
    )
    if not check.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Not a member")
    # Get all participants with user details
    stmt = (
        select(ChatParticipant, User)
        .join(User, ChatParticipant.user_id == User.id)
        .where(ChatParticipant.chat_id == group_id)
    )
    result = await db.execute(stmt)
    rows = result.all()
    participants = []
    for cp, user in rows:
        participants.append(
            ParticipantOut(
                user_id=user.id,
                name=user.name or user.phone_number,
                avatar_url=user.avatar_url,
                role=cp.role,
                joined_at=cp.joined_at,
            )
        )
    return participants
