# Detailed Development Plan – WhatsApp-like Chat Backend

This plan delivers all requested features incrementally, from a minimal viable product (MVP) to a production-ready system. Each phase is fully functional and can be deployed independently.

**Estimated total time**: 10–12 weeks (1 developer full‑time). Adjust based on team size.

---

## Phase 1: Foundation & User Management (Week 1)

**Goal**: Basic user authentication, profile management, and database setup.

### Tasks

1. **Project setup**
   - Initialize FastAPI project with Docker, Docker Compose.
   - Configure PostgreSQL, Redis, Celery (using Redis broker).
   - Set up environment variables and logging.

2. **Database schema (Phase 1)**
   - `users` table (id, phone_number, name, avatar_url, created_at)
   - `user_sessions` table (for JWT refresh tokens)

3. **Authentication & Registration**
   - OTP via phone number (using Twilio or mock for dev).
   - JWT access + refresh tokens.
   - Endpoints: `POST /auth/request-otp`, `POST /auth/verify-otp`, `POST /auth/refresh`.

4. **Profile management**
   - `GET /users/me`, `PATCH /users/me` (update name, avatar_url).

5. **Docker deployment**
   - Single `docker-compose.yml` with PostgreSQL, Redis, FastAPI, Celery worker.

### Deliverables

- Working user registration and login.
- Docker environment that runs `fastapi`, `postgres`, `redis`, `celery`.
- API documentation at `/docs`.

### Reasoning

Start with user identity – everything else depends on it. OTP avoids password complexity early. Docker ensures reproducible environment.

---

## Phase 2: 1-to-1 Messaging (WebSockets) (Weeks 2–3)

**Goal**: Real‑time private messaging with sent/delivered/read receipts.

### Tasks

1. **Database additions**
   - `chats` table (id, type='private', created_at)
   - `chat_participants` (chat_id, user_id, joined_at)
   - `messages` (id, chat_id, sender_id, text, status, created_at)
   - `message_deliveries` (for group later, but can start with per‑message status in main table for private).

2. **Connection Manager**
   - In‑memory `user_id -> WebSocket` mapping.
   - WebSocket endpoint `/ws?token=jwt` (authenticate via query param or upgrade header).
   - Heartbeat ping/pong.

3. **REST endpoints for messages**
   - `POST /chats/private/{other_user_id}` – create or get existing private chat.
   - `GET /chats` – list user's chats (with last message).
   - `GET /messages/{chat_id}?before=<timestamp>&limit=50` – paginated history.

4. **Real‑time message flow**
   - Client sends JSON over WebSocket: `{ type: "message", to_user_id, text, temp_id }`.
   - Server: Create chat if none, store message (status='sent'), find receiver's WebSocket, push message, update status to 'delivered'.
   - Client replies with `{ type: "read", message_id }` → server updates status to 'read' and notifies sender.

5. **Offline handling**
   - If receiver offline, message status remains 'sent'. Deliver when receiver connects (check unsent messages on reconnect).

### Deliverables

- Two users can chat in real‑time with typing indicators (base), read receipts.
- Message history retrieval.
- WebSocket reconnection with message catch‑up.

### Testing

- Two browser windows or WebSocket clients.
- Simulate network disconnect and reconnect.

---

## Phase 3: Presence & Typing Indicators (Week 4)

**Goal**: Online/offline status, last seen, typing notifications.

### Tasks

1. **Redis presence**
   - On WebSocket connect: `SETEX presence:{user_id} 35 "online"`.
   - Heartbeat every 25s: refresh TTL.
   - On disconnect (or after TTL expires): delete key, update `last_seen` in DB.
   - Endpoint `GET /users/{user_id}/presence` returns "online" or last seen timestamp.

2. **User‑facing presence**
   - In chat list and header, display status.
   - Subscribe to presence changes: when a user comes online, notify their contacts (optional – can be pull‑based).

3. **Typing indicators**
   - Client sends WebSocket message: `{ type: "typing", chat_id, is_typing: true }`.
   - Server stores in Redis: `SETEX typing:{chat_id}:{user_id} 1 "1"` (3s TTL).
   - Broadcast to other participants in that chat (via WebSocket): `{ "type": "typing", user_id, chat_id, is_typing: true }`.
   - Client sends `is_typing: false` on stop or rely on TTL.

### Deliverables

- Online/offline status shown in real time.
- "Typing..." indicator appears and disappears after 3s without updates.

### Reasoning

Presence and typing are real‑time requirements that rely on Redis for cross‑instance sync later. This phase also introduces TTL‑based state.

---

## Phase 4: Group Chats (Week 5)

**Goal**: Create groups, add/remove participants, admin roles, group messaging.

### Tasks

1. **Database updates**
   - Extend `chats` with `type='group'`, `group_name`, `group_avatar`.
   - `chat_participants` add `role` (admin, member) and `muted_until`.
   - `message_deliveries` table: `(message_id, user_id, status, delivered_at, read_at)`.

2. **Group management endpoints**
   - `POST /groups` – create group (creator becomes admin).
   - `POST /groups/{group_id}/participants` – add member (admin only).
   - `DELETE /groups/{group_id}/participants/{user_id}` – remove member (admin or self).
   - `PATCH /groups/{group_id}/participants/{user_id}/role` – change role.
   - `PATCH /groups/{group_id}` – update name/avatar.

3. **Group messaging**
   - Client sends message to `chat_id` (group). Server:
     - Insert one `messages` row.
     - Insert into `message_deliveries` one row per participant (except sender) with status='sent'.
     - For each online participant, push message via WebSocket; set status='delivered' in delivery table when ack from receiver.
   - Read receipt: when participant reads, update their `message_deliveries.read_at` and notify sender (only if message belongs to a chat where sender is participant).

4. **Performance optimisation**
   - Use `bulk_create` for message deliveries (Celery or async DB driver).
   - For large groups (1000+), fan‑out can be moved to a background task. Implement `delivery_method = "background"` toggle.

### Deliverables

- Users can create groups, add members, and send messages to the group.
- Each member sees deliveries and read receipts per message (if group size ≤ 200; larger groups may disable per‑user read status).

---

## Phase 5: Media & File Sharing (Weeks 6–7)

**Goal**: Send images, videos, documents, voice messages.

### Tasks

1. **Media storage**
   - Choose local storage for dev, S3/MinIO for production.
   - Install `boto3` and configure.

2. **Database additions**
   - `media` table: id, user_id, type, storage_path, thumbnail_path, mime_type, size_bytes, created_at.

3. **Upload endpoint**
   - `POST /media/upload` – accepts multipart file. Returns `media_id`.
   - FastAPI stream file to disk, then Celery task:
     - Generate thumbnail (using `Pillow` for images, `ffmpeg` for videos).
     - Upload to S3/local.
     - Store metadata in DB.
   - Client then sends message with `media_id`.

4. **Serving media**
   - `GET /media/{media_id}` – returns file (or redirect to S3 signed URL).
   - For thumbnails: `GET /media/{media_id}/thumbnail`.

5. **Voice messages**
   - Client records audio (Opus/MP3), uploads as file with type='audio'.
   - Server processes same as other media. No special handling.

6. **Message with media**
   - `messages.text` optional; `messages.media_id` references media.
   - In WebSocket push, include media URL and thumbnail.

### Deliverables

- Users can attach images/videos/audio to messages.
- Media displayed in chat history with thumbnails.
- Voice messages playable.

### Trade‑off

Media processing is async – user sees placeholder until upload completes. For small files (<1MB), you can process inline.

---

## Phase 6: Status (Stories) (Week 8)

**Goal**: 24‑hour disappearing posts (text, image, video) with viewer list.

### Tasks

1. **Database**
   - `statuses` (id, user_id, media_id, text, expires_at, created_at).
   - `status_views` (status_id, viewer_id, viewed_at).

2. **Endpoints**
   - `POST /status` – create a status (media or text). Set `expires_at = now() + 24h`.
   - `GET /status` – fetch statuses from users I haven't blocked, order by recency, group by user.
   - `GET /status/{status_id}/views` – list viewers (only for own status).
   - `POST /status/{status_id}/view` – mark as viewed.

3. **Background cleanup**
   - Celery periodic task (`celery beat`) to delete expired statuses and associated media.

4. **Privacy controls**
   - Allow user to select “My contacts” or “Close friends” when posting.
   - Store privacy setting in `statuses.privacy` and filter in query.

### Deliverables

- Users can post text/image/video stories that expire after 24h.
- Viewers list visible to author.
- Statuses appear in a dedicated row above chat list.

---

## Phase 7: Chat Management & Search (Week 9)

**Goal**: Pinned chats, starred messages, archive, search.

### Tasks

1. **Database additions**
   - `chat_participants` add `pinned` (boolean, default false), `archived` (boolean).
   - `messages` add `is_starred` (boolean, default false) but per‑user star: create `starred_messages` (user_id, message_id).

2. **Endpoints**
   - `PATCH /chats/{chat_id}/pin` – pin/unpin chat for current user.
   - `PATCH /chats/{chat_id}/archive` – archive/unarchive.
   - `POST /messages/{message_id}/star` – star/unstar.
   - `GET /messages/starred` – list starred messages.
   - `GET /messages/search?q=text` – full‑text search using PostgreSQL `tsvector` or `LIKE` (can add pgvector later for semantic).

3. **Real‑time updates**
   - When chat list changes (pin/archive), push WebSocket event `chat_list_update` so client refreshes.

### Deliverables

- Users can pin up to 5 chats at top.
- Archived chats hidden from main list.
- Search messages by keyword.

---

## Phase 8: Voice & Video Calls (Week 10 – advanced)

**Goal**: 1‑to‑1 VoIP, later group calls.

### Tasks (1‑to‑1 only)

1. **Signalling server**
   - Extend WebSocket protocol to handle call offers, answers, ICE candidates.
   - Message types: `call_offer`, `call_answer`, `ice_candidate`, `call_end`.

2. **Call state management**
   - Redis: `call:{call_id}` stores participants, state (ringing, active, ended) with TTL.
   - Notify callee via WebSocket (or push notification if offline).

3. **Media plane**
   - Use WebRTC with STUN/TURN servers (e.g., Coturn). Provide client with TURN credentials via REST endpoint `GET /calls/turn-credentials`.

4. **Group calls (optional extension)**
   - Requires SFU (Selective Forwarding Unit) like `mediasoup`. Out of scope for initial plan.

### Deliverables

- One‑to‑one audio and video calls with ringtone, accept/reject.
- Call history stored in `calls` table (duration, participants).

**Trade‑off**: WebRTC is client‑heavy; backend only handles signalling and TURN. Implementation complexity is moderate.

---

## Phase 9: Notifications & Security (Week 11)

**Goal**: Push notifications, per‑chat mute, block user, two‑step verification.

### Tasks

1. **Push notifications**
   - Integrate Firebase Cloud Messaging (FCM) for Android, APNS for iOS.
   - When message arrives and user offline (or not active in WebSocket), Celery sends push via FCM/APNS.
   - Store device tokens in `user_devices` table.

2. **Per‑chat notification settings**
   - `chat_participants` add `notify` (boolean, default true) and `mute_until` (timestamp).
   - When sending message, skip push if `mute_until > now()`.

3. **Block user**
   - `blocked_users` table (blocker_id, blocked_id).
   - Modify message sending: if either party blocked the other, reject.
   - Modify status/group participation checks.

4. **Two‑step verification**
   - Add `two_step_enabled` and `two_step_secret` (TOTP) to users table.
   - Endpoints: `POST /auth/2fa/enable`, `POST /auth/2fa/verify`.
   - On login, after OTP verification, require 2FA code if enabled.

### Deliverables

- Push notifications for new messages/calls.
- Users can mute individual chats permanently or for a duration.
- Blocking prevents communication.
- Two‑step verification improves security.

---

## Phase 10: Backup & Restore (Week 12)

**Goal**: Chat backups (end‑to‑end encrypted) and restore on new device.

### Tasks

1. **Backup design**
   - User‑initiated backup: client exports encrypted chat history to cloud storage (or server‑side backup).
   - For simplicity: server creates daily encrypted backup of user's messages (user can download).
   - Use AES‑256 with user password derived via PBKDF2 (client‑side encryption).

2. **Endpoints**
   - `POST /backup/export` – trigger backup, returns download URL.
   - `POST /backup/restore` – upload backup file, server restores messages (requires same user ID/phone number).

3. **Metadata backup**
   - Backup includes: messages, media references (not binary media), chat list, starred, pinned.
   - Media is separately backed up via storage provider's lifecycle policies.

4. **Restore on new device**
   - After login, prompt to restore from latest backup. Client downloads, decrypts, and re‑uploads messages via API.

### Deliverables

- Full chat history can be backed up and restored.
- No loss of data when switching devices.

---

## Cross‑cutting tasks (throughout phases)

- **Docker & deployment**: Every phase ensures `docker-compose up` works.
- **WebSocket scaling readiness**: Use Redis Pub/Sub as described for cross‑instance messaging, even on single node – easy to scale later.
- **Testing**: Unit tests for core logic, integration tests for API endpoints, WebSocket simulation.
- **API documentation**: Keep OpenAPI spec up to date.
- **Error handling & logging**: Structured JSON logs to stdout, captured by Loki.

---

## Final delivery checklist

- All features listed in the original prompt are implemented.
- System runs as a single Docker Compose stack on a single VM.
- Configuration through environment variables.
- Basic monitoring (Prometheus metrics) available.
- Production readiness notes: scaling by adding load balancer, multiple FastAPI replicas, and increasing Redis memory.

---
