from datetime import datetime
from uuid import UUID, uuid4

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from jose import JWTError
from sqlalchemy import func, select, update

from api.routes import auth, chats, health, media, messages, status, users
from db.models.call import Call, CallStatus
from db.models.chat import Chat, ChatParticipant, ChatType
from db.models.media import Media
from db.models.message import DeliveryStatus, Message, MessageDelivery, MessageStatus
from db.models.user import User
from db.session import AsyncSessionLocal
from services.websocket_manager import manager
from utils.call_manager import delete_call_state, get_call_state, set_call_state
from utils.presence import get_redis, set_online, update_last_seen
from utils.security import decode_token
from api.routes import calls

app = FastAPI(title="Chat App Backend", version="0.1.0")

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(chats.router)
app.include_router(messages.router)
app.include_router(media.router)
app.include_router(status.router)
app.include_router(calls.router)
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

        # -------------------- Deliver pending messages on reconnect --------------------
        # Private: pending messages where receiver is this user and status is 'sent'
        private_pending = (
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
        result = await db.execute(private_pending)
        for msg in result.scalars().all():
            payload = {
                "type": "message",
                "id": str(msg.id),
                "chat_id": str(msg.chat_id),
                "sender_id": str(msg.sender_id),
                "text": msg.text,
                "status": msg.status,
                "created_at": msg.created_at.isoformat(),
            }
            if msg.media_id:
                payload["media_id"] = str(msg.media_id)
            await manager.send_personal_message(
                user_id,
                payload,
            )
            msg.status = MessageStatus.DELIVERED

        # Group: pending deliveries for this user with status 'sent'
        group_pending = (
            select(MessageDelivery, Message)
            .join(Message, MessageDelivery.message_id == Message.id)
            .where(
                MessageDelivery.user_id == user_id,
                MessageDelivery.status == DeliveryStatus.SENT,
            )
        )
        result = await db.execute(group_pending)
        for delivery, msg in result.all():
            payload = {
                "type": "message",
                "id": str(msg.id),
                "chat_id": str(msg.chat_id),
                "sender_id": str(msg.sender_id),
                "text": msg.text,
                "created_at": msg.created_at.isoformat(),
            }
            if msg.media_id:
                payload["media_id"] = str(msg.media_id)
            await manager.send_personal_message(
                user_id,
                payload,
            )
            delivery.status = DeliveryStatus.DELIVERED
            delivery.delivered_at = func.now()

        await db.commit()

        # -------------------- Main loop --------------------
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "message":
                chat_id = UUID(data["chat_id"])
                text = data["text"]
                temp_id = data.get("temp_id")

                # Verify sender is a participant
                participant_check = await db.execute(
                    select(ChatParticipant).where(
                        ChatParticipant.chat_id == chat_id,
                        ChatParticipant.user_id == user_id,
                    )
                )
                if not participant_check.scalar_one_or_none():
                    await websocket.send_json(
                        {"type": "error", "message": "Not a participant"}
                    )
                    continue

                # Fetch chat
                chat = await db.get(Chat, chat_id)
                if not chat:
                    await websocket.send_json(
                        {"type": "error", "message": "Chat not found"}
                    )
                    continue

                # Optional media attachment
                media_id = data.get("media_id")
                if media_id:
                    media_id = UUID(media_id)
                    media_obj = await db.get(Media, media_id)
                    if not media_obj or media_obj.user_id != user_id:
                        await websocket.send_json(
                            {"type": "error", "message": "Invalid media_id"}
                        )
                        continue

                # Create the message
                msg = Message(
                    chat_id=chat_id,
                    sender_id=user_id,
                    text=text,
                    media_id=media_id,
                    status=(
                        MessageStatus.SENT if chat.type == ChatType.PRIVATE else None
                    ),
                )
                db.add(msg)
                await db.flush()

                if chat.type == ChatType.PRIVATE:
                    # Find the other participant (receiver)
                    other_participant = await db.execute(
                        select(ChatParticipant.user_id).where(
                            ChatParticipant.chat_id == chat_id,
                            ChatParticipant.user_id != user_id,
                        )
                    )
                    receiver_id = other_participant.scalar_one()
                    await db.commit()

                    # Try to deliver
                    payload = {
                        "type": "message",
                        "id": str(msg.id),
                        "chat_id": str(chat_id),
                        "sender_id": str(user_id),
                        "text": text,
                        "status": "sent",
                        "created_at": msg.created_at.isoformat(),
                    }
                    if media_id:
                        payload["media_id"] = str(media_id)
                    delivered = await manager.send_personal_message(
                        receiver_id,
                        payload,
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

                else:  # Group
                    # Get all participants except sender
                    participants = await db.execute(
                        select(ChatParticipant.user_id).where(
                            ChatParticipant.chat_id == chat_id,
                            ChatParticipant.user_id != user_id,
                        )
                    )
                    participant_ids = participants.scalars().all()

                    # Create message deliveries
                    deliveries = []
                    for pid in participant_ids:
                        deliveries.append(
                            MessageDelivery(
                                message_id=msg.id,
                                user_id=pid,
                                status=DeliveryStatus.SENT,
                            )
                        )
                    db.add_all(deliveries)
                    await db.commit()

                    # For each online participant, send and update delivery status
                    group_payload = {
                        "type": "message",
                        "id": str(msg.id),
                        "chat_id": str(chat_id),
                        "sender_id": str(user_id),
                        "text": text,
                        "created_at": msg.created_at.isoformat(),
                    }
                    if media_id:
                        group_payload["media_id"] = str(media_id)
                    for pid in participant_ids:
                        online = await manager.send_personal_message(
                            pid,
                            group_payload,
                        )
                        if online:
                            await db.execute(
                                update(MessageDelivery)
                                .where(
                                    MessageDelivery.message_id == msg.id,
                                    MessageDelivery.user_id == pid,
                                )
                                .values(
                                    status=DeliveryStatus.DELIVERED,
                                    delivered_at=func.now(),
                                )
                            )
                    await db.commit()

                    # Acknowledge sender
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
                chat_id = UUID(data.get("chat_id", ""))
                msg = await db.get(Message, message_id)

                if not msg:
                    await websocket.send_json(
                        {"type": "error", "message": "Message not found"}
                    )
                    continue

                # Determine chat type to handle read receipt appropriately
                chat = await db.get(Chat, msg.chat_id)

                if chat and chat.type == ChatType.PRIVATE:
                    # Private: update message status directly and notify sender
                    if msg.sender_id != user_id:
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
                elif chat and chat.type == ChatType.GROUP:
                    # Group: update the delivery entry for this user
                    await db.execute(
                        update(MessageDelivery)
                        .where(
                            MessageDelivery.message_id == message_id,
                            MessageDelivery.user_id == user_id,
                        )
                        .values(read_at=func.now())
                    )
                    await db.commit()

                    # Notify the sender that this user read it
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
                r = await get_redis()
                if is_typing:
                    await r.setex(f"typing:{chat_id}:{user_id}", 3, "1")
                else:
                    await r.delete(f"typing:{chat_id}:{user_id}")

                # Broadcast to other participants
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
                await websocket.send_json({"type": "heartbeat_ack"})

            elif msg_type == "call_offer":
                # payload: { chat_id, call_type, sdp, call_id (optional) }
                chat_id = UUID(data["chat_id"])
                call_type = data["call_type"]  # "audio" or "video"
                sdp = data["sdp"]

                # Find other participant in chat (private chat only)
                other_user = await db.execute(
                    select(ChatParticipant.user_id).where(
                        ChatParticipant.chat_id == chat_id,
                        ChatParticipant.user_id != user_id,
                    )
                )
                other_user_id = other_user.scalar_one_or_none()
                if not other_user_id:
                    await websocket.send_json(
                        {"type": "error", "message": "Invalid chat"}
                    )
                    continue

                # Generate call_id if not provided
                call_id = UUID(data.get("call_id", str(uuid4())))

                # Store call in DB
                call = Call(
                    id=call_id,
                    initiator_id=user_id,
                    receiver_id=other_user_id,
                    call_type=call_type,
                    status=CallStatus.RINGING,
                )
                db.add(call)
                await db.commit()

                # Store temporary state in Redis
                await set_call_state(
                    call_id,
                    {
                        "chat_id": str(chat_id),
                        "initiator": str(user_id),
                        "receiver": str(other_user_id),
                        "call_type": call_type,
                        "status": "ringing",
                        "offer_sdp": sdp,
                        "created_at": datetime.utcnow().isoformat(),
                    },
                )

                # Send offer to receiver
                sent = await manager.send_personal_message(
                    other_user_id,
                    {
                        "type": "call_offer",
                        "call_id": str(call_id),
                        "caller_id": str(user_id),
                        "caller_name": user.name or user.phone_number,
                        "chat_id": str(chat_id),
                        "call_type": call_type,
                        "sdp": sdp,
                    },
                )
                if not sent:
                    # Receiver offline – mark call as missed and notify caller
                    call.status = CallStatus.MISSED
                    call.ended_at = func.now()
                    await db.commit()
                    await websocket.send_json(
                        {"type": "call_error", "reason": "receiver_offline"}
                    )
                else:
                    await websocket.send_json(
                        {"type": "call_ringing", "call_id": str(call_id)}
                    )

            elif msg_type == "call_answer":
                call_id = UUID(data["call_id"])
                sdp = data["sdp"]
                state = await get_call_state(call_id)
                if not state:
                    await websocket.send_json(
                        {"type": "error", "message": "Call not found"}
                    )
                    continue

                # Update call in DB
                call = await db.get(Call, call_id)
                if call:
                    call.status = CallStatus.ACTIVE
                    call.started_at = datetime.utcnow()
                    await db.commit()

                # Update Redis state
                state["status"] = "active"
                state["answer_sdp"] = sdp
                await set_call_state(call_id, state)

                # Forward answer to initiator
                initiator_id = UUID(state["initiator"])
                await manager.send_personal_message(
                    initiator_id,
                    {
                        "type": "call_answer",
                        "call_id": str(call_id),
                        "sdp": sdp,
                    },
                )

            elif msg_type == "ice_candidate":
                call_id = UUID(data["call_id"])
                candidate = data["candidate"]
                sdp_mid = data.get("sdpMid")
                sdp_mline_index = data.get("sdpMLineIndex")

                state = await get_call_state(call_id)
                if not state:
                    continue

                # Determine target: if current user is initiator, send to receiver, else to initiator
                target_id = (
                    UUID(state["receiver"])
                    if user_id == UUID(state["initiator"])
                    else UUID(state["initiator"])
                )
                await manager.send_personal_message(
                    target_id,
                    {
                        "type": "ice_candidate",
                        "call_id": str(call_id),
                        "candidate": candidate,
                        "sdpMid": sdp_mid,
                        "sdpMLineIndex": sdp_mline_index,
                    },
                )

            elif msg_type == "call_end":
                call_id = UUID(data["call_id"])
                state = await get_call_state(call_id)
                if not state:
                    continue

                # Update call in DB
                call = await db.get(Call, call_id)
                if call and call.status == CallStatus.ACTIVE:
                    call.status = CallStatus.ENDED
                    call.ended_at = datetime.utcnow()
                    if call.started_at:
                        delta = call.ended_at - call.started_at
                        call.duration_seconds = int(delta.total_seconds())
                    await db.commit()

                # Delete Redis state
                await delete_call_state(call_id)

                # Notify the other participant
                other_id = (
                    UUID(state["receiver"])
                    if user_id == UUID(state["initiator"])
                    else UUID(state["initiator"])
                )
                await manager.send_personal_message(
                    other_id,
                    {
                        "type": "call_end",
                        "call_id": str(call_id),
                    },
                )

            elif msg_type == "call_reject":
                call_id = UUID(data["call_id"])
                state = await get_call_state(call_id)
                if not state:
                    continue

                # Update call in DB
                call = await db.get(Call, call_id)
                if call:
                    call.status = CallStatus.REJECTED
                    call.ended_at = datetime.utcnow()
                    await db.commit()

                # Notify initiator
                initiator_id = UUID(state["initiator"])
                await manager.send_personal_message(
                    initiator_id,
                    {
                        "type": "call_reject",
                        "call_id": str(call_id),
                    },
                )
                await delete_call_state(call_id)

    except WebSocketDisconnect:
        manager.disconnect(user_id)
    finally:
        await update_last_seen(user_id, db)
        await db.close()
