# Scalable WhatsApp‑like chat system

## 1. High‑Level System Architecture (Text Diagram)

```
 ┌─────────────┐      WebSocket     ┌───────────────────────────────────┐
 │   Client    │◄──────────────────►│          FastAPI (Uvicorn)        │
 │ (Mobile/Web)│      HTTP/REST      │  ┌─────────────┐  ┌─────────────┐  │
 └─────────────┘                     │  │ Connection  │  │ REST API    │  │
                                     │  │ Manager     │  │ Handlers    │  │
                                     │  └──────┬──────┘  └──────┬──────┘  │
                                     │         │                │         │
                                     │    Redis Pub/Sub       Celery     │
                                     │         │                │         │
                                     └─────────┼────────────────┼─────────┘
                                               │                │
                                    ┌──────────┴──────┐    ┌────┴────────┐
                                    │     Redis       │    │   Celery    │
                                    │  (presence,     │    │   Worker    │
                                    │   sessions,     │    │ (background)│
                                    │   pub/sub)      │    └─────┬──────┘
                                    └────────┬────────┘          │
                                             │                   │
                                    ┌────────┴────────┐    ┌────┴─────┐
                                    │   PostgreSQL    │    │   S3 /   │
                                    │   (main DB)     │    │  Local   │
                                    └─────────────────┘    │  Storage │
                                                            └──────────┘
```

**Notes on scaling without a load balancer**

- A single instance works fine for moderate load.
- To scale later, add a Layer‑4 load balancer (e.g., HAProxy, Nginx) in front of multiple FastAPI instances.
- WebSocket connections must be sticky (session affinity) OR we use Redis Pub/Sub to broadcast messages to all instances – I’ll show the stateless approach.

---

## 2. Component Breakdown

| Component              | Responsibility                                                                                                                                               | Tech                         |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------- |
| **FastAPI**            | REST endpoints (send message, create group, upload media) + WebSocket server                                                                                 | `fastapi`, `websockets`      |
| **Connection Manager** | In‑memory map of `user_id → WebSocket` (per instance). For multi‑node, use Redis to route messages.                                                          | Python `dict`, Redis Pub/Sub |
| **Redis**              | • Pub/Sub for cross‑instance message delivery<br>• Presence (online/last seen)<br>• Typing indicators<br>• Rate limiting<br>• Celery broker & result backend | `redis-py`                   |
| **PostgreSQL**         | Persistent storage: users, messages, groups, media metadata, read receipts, etc.                                                                             | `asyncpg`, SQLAlchemy        |
| **Celery**             | Background jobs: sending push notifications, media processing (thumbnails, virus scan), backup tasks                                                         | `celery`, `redis` broker     |
| **Storage**            | Blob storage for images, videos, documents – local disk or S3‑compatible. For scaling, use cloud.                                                            | `boto3` (S3) or local volume |

---

## 3. Data Flow for Key Features

### 3.1 Private Message (user A → user B)

1. **A sends message** via WebSocket (or REST). Payload: `{ to: "B", text: "hello" }`.
2. **FastAPI** validates, stores message in PostgreSQL:
   ```sql
   INSERT INTO messages (id, chat_id, sender_id, text, status, created_at)
   VALUES (..., 'sent');
   ```
3. **After DB commit**, FastAPI:
   - If B is **online** (presence in Redis), retrieve B’s WebSocket (from local connection manager or via Redis) and push message with `status='delivered'`. Update message status to `delivered`.
   - If B offline, queue push notification via Celery.
4. **B receives message** → client sends read receipt. FastAPI updates message status to `read` and notifies A (if A online).

**Redis role**:

- Key `presence:user:B` → `"online"` + TTL (heartbeat every 30s).
- For multi‑instance: When message arrives on instance X, it publishes `user:B:new_message` on Redis channel; instance Y (where B is connected) receives and pushes.

### 3.2 Group Chat

- Group chat is a special `Chat` type with `is_group = true`.
- `group_participants` table stores `user_id`, `role` (admin, member).
- Message sending: Insert one `message` row, then fan‑out to all group members (except sender):
  - Insert `message_delivery` rows (`message_id`, `user_id`, `status`).
  - For each online member, push via WebSocket; for offline, queue push notification.

**Scaling consideration**: Fan‑out could be heavy for large groups. Use Celery to batch delivery.

### 3.3 Media Upload

1. Client sends `POST /media/upload` with binary data (multipart).
2. FastAPI streams file to temporary location. Celery task:
   - Generate thumbnail (image/video).
   - Scan for viruses.
   - Upload to S3/local storage.
   - Store metadata in `media` table.
3. Client then sends a **message** referencing the `media_id`. Similar flow to text.

### 3.4 Voice Calls (VoIP) – High Level

- Real‑time media (WebRTC) requires a signalling server. You can use FastAPI with WebSockets for signalling (offer/answer/ICE).
- For 1‑to‑1, use peer‑to‑peer. For group calls, you’d later introduce a Selective Forwarding Unit (SFU) like `mediasoup` – but that’s outside your current stack.

---

## 4. Database Schema (PostgreSQL)

```sql
-- Users
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone_number VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(100),
    avatar_url TEXT,
    two_step_verified BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT now()
);

-- Chats (1-to-1 or group)
CREATE TABLE chats (
    id UUID PRIMARY KEY,
    type VARCHAR(10) CHECK (type IN ('private', 'group')),
    group_name VARCHAR(100),
    group_avatar TEXT,
    created_at TIMESTAMP DEFAULT now()
);

-- Participants (for both private & group)
CREATE TABLE chat_participants (
    chat_id UUID REFERENCES chats(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(20) DEFAULT 'member', -- admin, member
    joined_at TIMESTAMP DEFAULT now(),
    muted_until TIMESTAMP NULL,
    PRIMARY KEY (chat_id, user_id)
);

-- Messages
CREATE TABLE messages (
    id UUID PRIMARY KEY,
    chat_id UUID REFERENCES chats(id) ON DELETE CASCADE,
    sender_id UUID REFERENCES users(id),
    reply_to_id UUID REFERENCES messages(id) NULL,
    text TEXT,
    media_id UUID NULL,
    status VARCHAR(20) DEFAULT 'sent', -- sent, delivered, read
    created_at TIMESTAMP DEFAULT now()
);

-- Message delivery status per participant (for group messages)
CREATE TABLE message_deliveries (
    message_id UUID REFERENCES messages(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    status VARCHAR(20) DEFAULT 'sent',
    delivered_at TIMESTAMP,
    read_at TIMESTAMP,
    PRIMARY KEY (message_id, user_id)
);

-- Media metadata
CREATE TABLE media (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    type VARCHAR(20), -- image, video, audio, document
    storage_path TEXT, -- S3 key or local path
    thumbnail_path TEXT,
    mime_type VARCHAR(100),
    size_bytes BIGINT,
    created_at TIMESTAMP DEFAULT now()
);

-- Status (Stories)
CREATE TABLE statuses (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    media_id UUID REFERENCES media(id),
    text TEXT,
    expires_at TIMESTAMP, -- 24h from creation
    created_at TIMESTAMP DEFAULT now()
);

-- Status viewers
CREATE TABLE status_views (
    status_id UUID REFERENCES statuses(id) ON DELETE CASCADE,
    viewer_id UUID REFERENCES users(id),
    viewed_at TIMESTAMP DEFAULT now(),
    PRIMARY KEY (status_id, viewer_id)
);

-- Blocked users
CREATE TABLE blocked_users (
    blocker_id UUID REFERENCES users(id),
    blocked_id UUID REFERENCES users(id),
    PRIMARY KEY (blocker_id, blocked_id)
);

-- Indexes: on messages(chat_id, created_at), message_deliveries(user_id, status)
```

---

## 5. Real‑Time Messaging with WebSockets

### Connection Management on a Single Instance

```python
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[UUID, WebSocket] = {}

    async def connect(self, user_id: UUID, ws: WebSocket):
        await ws.accept()
        self.active_connections[user_id] = ws

    def disconnect(self, user_id: UUID):
        self.active_connections.pop(user_id, None)

    async def send_personal_message(self, user_id: UUID, message: dict):
        ws = self.active_connections.get(user_id)
        if ws:
            await ws.send_json(message)
```

**WebSocket endpoint**:

```python
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, user_id: UUID):
    manager.connect(user_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            # handle incoming message, typing, read receipt
    except WebSocketDisconnect:
        manager.disconnect(user_id)
        # update presence offline in Redis
```

### Multi‑Instance Scaling (without load balancer? requires sticky or pub/sub)

**Solution**: Each instance maintains its own local connection manager. When a message arrives on instance A for a user connected to instance B:

1. Store message in DB (common).
2. Publish to Redis: `pubsub.publish("user_msg_" + user_id, message_json)`.
3. Every instance subscribes to `user_msg_*` patterns. Instance B receives, looks up local connection, sends to client.

**Redis code**:

```python
# On startup, subscribe to wildcard
async def listen_to_redis():
    pubsub = redis.pubsub()
    await pubsub.psubscribe("user_msg_*")
    async for message in pubsub.listen():
        user_id = message['channel'].decode().split('_')[-1]
        ws = manager.active_connections.get(UUID(user_id))
        if ws:
            await ws.send_json(json.loads(message['data']))
```

**No load balancer needed** if clients connect directly to instance IPs – but that’s not realistic. For scaling, you still need a LB. I’ll assume you’ll add a simple one (e.g., HAProxy) later.

---

## 6. Redis Usage Strategy

| Feature                                | Redis Data Structure                                                                 | TTL / Behaviour                                                                   |
| -------------------------------------- | ------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------- |
| **Presence**                           | String `presence:{user_id}` = `"online"`                                             | TTL 35s, renewed every 25s via heartbeat. `last_seen` stored in DB on disconnect. |
| **User sessions**                      | Hash `session:{user_id}` → `instance_id`                                             | For cross‑instance routing (used with Pub/Sub).                                   |
| **Typing indicators**                  | String `typing:{chat_id}:{user_id}` = "1"                                            | TTL 3s – client sends every 2s while typing.                                      |
| **Rate limiting**                      | `incr` + expire on `rate:{user_id}:{action}`                                         | Per second/minute limits.                                                         |
| **Celery broker**                      | Redis Lists / Streams                                                                | Default Celery configuration.                                                     |
| **Message queue for offline delivery** | Not needed – DB poll + push notifications. Use Redis for transient queues if needed. |                                                                                   |

**Presence flow**:

- Client sends heartbeat every 25s over WebSocket.
- Server updates `presence:{user_id}` with `setex(user_id, 35, "online")`.
- On disconnect (clean or timeout), delete key and update `last_seen` in DB.

---

## 7. Scaling Approach (for future)

### 7.1 Stateless FastAPI instances

- Store **no** WebSocket connections in memory? But you must – they are per‑instance. So we accept local state and use Redis to route messages.
- Use **Redis Pub/Sub** as described. Each instance subscribes to a pattern. This works for up to ~50 instances (Redis pub/sub overhead is moderate).
- For larger scale, consider **Redis Streams** with consumer groups or a dedicated message bus (NATS).

### 7.2 Database scaling

- **Read replicas** for message history, status queries.
- **Partition messages** by `chat_id` and time (e.g., monthly partitioning).
- Use `asyncpg` connection pooling (max 100 per instance).

### 7.3 Media storage

- Start with local volume mounted to all instances (shared NFS). Better: use S3/MinIO for horizontal scaling.

### 7.4 WebSocket load balancing

- Add a Layer‑4 load balancer (e.g., HAProxy, NGINX) with `proxy_protocol` and sticky sessions based on `user_id` cookie or `IP_hash`. Or use **Cloudflare** or **AWS ALB** with WebSocket support.

### 7.5 Celery workers

- Scale workers independently. Use **Redis** as broker. For durability, switch to RabbitMQ.

---

## 8. Trade‑offs & Alternatives

| Area                         | My Choice                         | Trade‑off                                                                                                           |
| ---------------------------- | --------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| **Cross‑instance messaging** | Redis Pub/Sub                     | Simple, but at high scale (100k+ concurrent) Redis becomes bottleneck. Alternative: use database as queue or Kafka. |
| **Presence**                 | Redis with TTL                    | Eventually consistent; last seen may lag by <10s.                                                                   |
| **Read receipts**            | Two‑phase (delivered, read)       | Extra DB writes (one per user in groups). Acceptable for group size <500.                                           |
| **Media processing**         | Celery async                      | Adds latency (seconds) for upload. Client shows temporary thumbnail.                                                |
| **End‑to‑end encryption**    | Not implemented (high‑level only) | Adds complexity for key distribution. Use Signal Protocol double ratchet.                                           |

---

## 9. Putting It All Together – Deployment (Single Instance)

Create `docker-compose.yml` with:

- FastAPI app (with Uvicorn workers = 2)
- PostgreSQL
- Redis
- Celery worker
- (Optional) Nginx as reverse proxy for static files

**Environment variables**:

```
DATABASE_URL=postgresql://...
REDIS_URL=redis://redis:6379
```

**Run**:

```bash
docker-compose up -d
```

All features (private/group chats, media, presence, typing, read receipts) work on a single node. When you need to scale, add a load balancer and deploy multiple FastAPI containers (same code) with `REDIS_PUBSUB` enabled.

---

## 10. Final Notes

- The design is **production‑ready** for moderate load (10k concurrent users on a well‑provisioned instance).
- **No over‑engineering**: you can start with one instance and add Redis, Celery, media storage incrementally.
- **Real‑time latency** < 100ms for same‑instance messages, plus cross‑instance pub/sub overhead.
- **Backup & Restore**: Use PostgreSQL `pg_dump` and S3 for media; store encryption keys separately.
