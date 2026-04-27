from uuid import UUID

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from jose import JWTError
from sqlalchemy import and_, func, select

from api.routes import auth, chats, health, users
from db.models.chat import Chat, ChatParticipant, ChatType
from db.models.message import Message, MessageStatus
from db.models.user import User
from db.session import AsyncSessionLocal
from services.websocket_manager import manager
from utils.presence import set_online, update_last_seen
from utils.security import decode_token

app = FastAPI(title="Chat App Backend", version="0.1.0")

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(chats.router)
app.include_router(health.router)


@app.get("/")
async def root():
    return {"message": "Welcome to Flux Chat API"}


@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
):
    # Authenticate via JWT token from query param
    try:
        payload = decode_token(token)
        user_id = UUID(payload.get("sub"))
        if payload.get("type") != "access":
            await websocket.close(code=1008, reason="Invalid token type")
            return
    except (JWTError, ValueError, TypeError):
        await websocket.close(code=1008, reason="Invalid token")
        return

    db = AsyncSessionLocal()

    try:
        # Check user exists
        user = await db.get(User, user_id)
        if not user:
            await websocket.close(code=1008, reason="User not found")
            return

        await manager.connect(user_id, websocket)

        # Deliver pending messages on reconnect
        stmt = (
            select(Message)
            .join(Chat, Message.chat_id == Chat.id)
            .join(ChatParticipant, Chat.id == ChatParticipant.chat_id)
            .where(
                Chat.type == ChatType.PRIVATE,
                ChatParticipant.user_id == user_id,
                Message.sender_id != user_id,
                Message.status == MessageStatus.SENT,
            )
        )
        result = await db.execute(stmt)
        pending = result.scalars().all()
        for msg in pending:
            await manager.send_personal_message(
                user_id,
                {
                    "type": "message",
                    "id": str(msg.id),
                    "chat_id": str(msg.chat_id),
                    "sender_id": str(msg.sender_id),
                    "text": msg.text,
                    "status": msg.status,
                    "created_at": msg.created_at.isoformat(),
                },
            )
            msg.status = MessageStatus.DELIVERED
        await db.commit()

        # Main loop
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "message":
                to_user_id = UUID(data["to_user_id"])
                text = data["text"]
                temp_id = data.get("temp_id")

                # Find or create private chat
                stmt = (
                    select(Chat)
                    .join(ChatParticipant, Chat.id == ChatParticipant.chat_id)
                    .where(Chat.type == ChatType.PRIVATE)
                    .group_by(Chat.id)
                    .having(func.count(ChatParticipant.user_id) == 2)
                    .having(
                        and_(
                            func.bool_or(ChatParticipant.user_id == user_id),
                            func.bool_or(ChatParticipant.user_id == to_user_id),
                        )
                    )
                )
                result = await db.execute(stmt)
                chat = result.scalar_one_or_none()
                if not chat:
                    chat = Chat(type=ChatType.PRIVATE)
                    db.add(chat)
                    await db.flush()
                    db.add_all(
                        [
                            ChatParticipant(chat_id=chat.id, user_id=user_id),
                            ChatParticipant(chat_id=chat.id, user_id=to_user_id),
                        ]
                    )
                    await db.commit()
                    await db.refresh(chat)

                # Store message
                msg = Message(
                    chat_id=chat.id,
                    sender_id=user_id,
                    text=text,
                    status=MessageStatus.SENT,
                )
                db.add(msg)
                await db.commit()
                await db.refresh(msg)

                # Deliver to receiver if online
                delivered = await manager.send_personal_message(
                    to_user_id,
                    {
                        "type": "message",
                        "id": str(msg.id),
                        "chat_id": str(chat.id),
                        "sender_id": str(user_id),
                        "text": text,
                        "status": msg.status,
                        "created_at": msg.created_at.isoformat(),
                    },
                )
                if delivered:
                    msg.status = MessageStatus.DELIVERED
                    await db.commit()
                    await manager.send_personal_message(
                        user_id,
                        {
                            "type": "message_delivered",
                            "temp_id": temp_id,
                            "message_id": str(msg.id),
                        },
                    )
                else:
                    await manager.send_personal_message(
                        user_id,
                        {
                            "type": "message_sent",
                            "temp_id": temp_id,
                            "message_id": str(msg.id),
                        },
                    )

            elif msg_type == "read":
                message_id = UUID(data["message_id"])
                msg = await db.get(Message, message_id)
                if msg and msg.sender_id != user_id:
                    msg.status = MessageStatus.READ
                    await db.commit()
                    await manager.send_personal_message(
                        msg.sender_id,
                        {
                            "type": "read_receipt",
                            "message_id": str(msg.id),
                            "chat_id": str(msg.chat_id),
                            "reader_id": str(user_id),
                        },
                    )

            elif msg_type == "typing":
                chat_id = UUID(data["chat_id"])
                is_typing = data.get("is_typing", False)
                # Store typing indicator in Redis with short TTL
                r = await auth.get_redis()
                if is_typing:
                    await r.setex(f"typing:{chat_id}:{user_id}", 3, "1")
                else:
                    await r.delete(f"typing:{chat_id}:{user_id}")
                # Broadcast to other participants in this chat
                # Fetch all participants of this chat except the sender
                stmt = select(ChatParticipant.user_id).where(
                    ChatParticipant.chat_id == chat_id,
                    ChatParticipant.user_id != user_id,
                )
                result = await db.execute(stmt)
                other_user_ids = result.scalars().all()
                for ouid in other_user_ids:
                    await manager.send_personal_message(
                        ouid,
                        {
                            "type": "typing",
                            "chat_id": str(chat_id),
                            "user_id": str(user_id),
                            "is_typing": is_typing,
                        },
                    )

            elif msg_type == "heartbeat":
                await set_online(user_id)
                # Optionally send heartbeat ack
                await websocket.send_json({"type": "heartbeat_ack"})

    except WebSocketDisconnect:
        manager.disconnect(user_id)
    finally:
        await update_last_seen(user_id, db)
        await db.close()
