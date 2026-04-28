# Flux Chat — Scalable WhatsApp-like Chat Backend

[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791.svg)](https://postgresql.org)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D.svg)](https://redis.io)
[![Celery](https://img.shields.io/badge/Celery-5.3-37814A.svg)](https://docs.celeryq.dev)
[![Docker](https://img.shields.io/badge/Docker-257bd6?logo=docker&logoColor=white)](https://docker.com)

A production-ready real‑time messaging backend built with **FastAPI**, **WebSockets**, **PostgreSQL**, **Redis**, and **Celery**.  
Supports private and group messaging, media sharing, voice/video calls, status updates, and more.

---

## Features

### Messaging

- **1‑to‑1 private chat** with real‑time delivery via WebSockets
- **Group chats** with admin roles, participant management, and per‑user message delivery tracking
- **Read receipts** (sent → delivered → read)
- **Typing indicators** (live via Redis TTL)
- **Offline message delivery** – pending messages are delivered on reconnect
- **Message history** with cursor‑based pagination

### Media & Files

- **Image/video/audio/document uploads** with async thumbnail generation (Pillow + ffmpeg)
- **Local & S3‑compatible storage** (configurable)
- **Voice messages**
- `GET /media/{id}` and `GET /media/{id}?thumbnail=true`

### Presence & Status

- **Online/offline presence** via Redis with heartbeat (25s interval, 35s TTL)
- **Last seen** timestamp persisted on disconnect
- **Status (Stories)** – text, image, or video posts that expire after 24 hours
- **Viewer tracking** – see who viewed your status
- **Privacy controls** – “My Contacts” or “Close Friends”

### Voice & Video Calls

- **WebRTC signalling** over WebSocket (`call_offer`, `call_answer`, `ice_candidate`, `call_end`, `call_reject`)
- **Call state** managed in Redis with TTL
- **TURN credentials** endpoint for production deployment
- **Call history** with duration tracking

### Chat Management

- **Pin/unpin chats**
- **Archive/unarchive chats**
- **Star/unstar messages**
- **Full‑text search** across your messages
- **Per‑chat mute** (permanent or timed)

### Notifications & Security

- **Push notifications** via Firebase Cloud Messaging (FCM)
- **Block user** – two‑way blocking prevents all communication
- **Two‑step verification** (TOTP via pyotp)
- **JWT authentication** (access + refresh tokens)
- **OTP‑based login** via phone number

### Backup & Restore

- **Export** your chat history as JSON
- **Restore** from backup (encrypted client‑side)

---

## Tech Stack

| Component              | Technology              | Purpose                                                          |
| ---------------------- | ----------------------- | ---------------------------------------------------------------- |
| **API Server**         | FastAPI (Uvicorn)       | REST endpoints + WebSocket server                                |
| **Database**           | PostgreSQL 15 (asyncpg) | Persistent storage                                               |
| **Cache / Real‑time**  | Redis 7                 | Presence, typing, call state, Celery broker & backend            |
| **Background Tasks**   | Celery 5.3              | Thumbnail generation, push notifications, expired status cleanup |
| **ORM**                | SQLAlchemy 2.0 (async)  | Database models and queries                                      |
| **Migrations**         | Alembic                 | Schema versioning                                                |
| **Auth**               | python‑jose + passlib   | JWT tokens, password hashing                                     |
| **Media Processing**   | Pillow + ffmpeg         | Thumbnails for images and videos                                 |
| **Push Notifications** | Firebase Admin SDK      | FCM for Android, APNs via FCM for iOS                            |
| **WebRTC**             | browser/client‑side     | STUN (Google public), TURN (self‑hosted Coturn)                  |

---

## Architecture Overview

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

**Key design decisions:**

- **Single‑instance first** – works out of the box with `docker compose up`
- **Redis Pub/Sub** for cross‑instance message routing when scaling
- **Async everywhere** – FastAPI async endpoints, async SQLAlchemy, async Redis
- **Celery** for non‑real‑time background tasks only (media, push, cleanup)

---

## Quick Start

### Prerequisites

- Docker & Docker Compose (v2+)
- Python 3.11+ (optional, for local development)

### Run with Docker (recommended)

```bash
git clone https://github.com/eddgachi/flux-chat-fastapi-backend
cd flux-chat-fastapi-backend

cp .env.example .env
docker compose up -d --build

docker compose logs -f app
```

The app will be available at **http://localhost:8000**.

| Service     | Port | URL                        |
| ----------- | ---- | -------------------------- |
| FastAPI App | 8000 | http://localhost:8000      |
| API Docs    | 8000 | http://localhost:8000/docs |
| PostgreSQL  | 5432 | localhost:5432             |
| Redis       | 6379 | localhost:6379             |

### First‑time setup

On first run, the app automatically runs database migrations (`alembic upgrade head`).  
To seed **Kenyan demo data** (8 users with private chats and group conversations):

```bash
docker compose exec app python seed_data.py
```

### Demo Users

| Name              | Phone Number  |
| ----------------- | ------------- |
| Wanjiku Kamau     | +254712345678 |
| Omondi Otieno     | +254723456789 |
| Achieng’ Nyambura | +254734567890 |
| Kiprop Chebet     | +254745678901 |
| Mwende Mutua      | +254756789012 |
| Barasa Wekesa     | +254767890123 |
| Nyokabi Maina     | +254778901234 |
| Juma Mwangi       | +254789012345 |

> **Note:** Seed data is only created once. To re‑seed, delete the database volume:  
> `docker compose down -v && docker compose up -d && docker compose exec app python seed_data.py`

---

## API Endpoints

### Authentication (`/auth`)

| Method | Endpoint            | Description                  |
| ------ | ------------------- | ---------------------------- |
| POST   | `/auth/request-otp` | Request OTP for phone number |
| POST   | `/auth/verify-otp`  | Verify OTP and get tokens    |
| POST   | `/auth/refresh`     | Refresh access token         |
| POST   | `/auth/2fa/enable`  | Enable two‑step verification |
| POST   | `/auth/2fa/verify`  | Verify 2FA code              |

### Users (`/users`)

| Method | Endpoint                    | Description                   |
| ------ | --------------------------- | ----------------------------- |
| GET    | `/users/me`                 | Get current user profile      |
| PATCH  | `/users/me`                 | Update profile (name, avatar) |
| GET    | `/users/{user_id}/presence` | Get online status             |
| GET    | `/users/contacts`           | Get contact list              |

### Chats (`/chats`)

| Method | Endpoint                   | Description                           |
| ------ | -------------------------- | ------------------------------------- |
| GET    | `/chats`                   | List user’s chats (with last message) |
| POST   | `/chats/private/{user_id}` | Create or get private chat            |
| PATCH  | `/chats/{chat_id}/pin`     | Pin/unpin chat                        |
| PATCH  | `/chats/{chat_id}/archive` | Archive/unarchive                     |
| PATCH  | `/chats/{chat_id}/mute`    | Mute/unmute chat                      |

### Messages (`/messages`)

| Method | Endpoint                      | Description                     |
| ------ | ----------------------------- | ------------------------------- |
| GET    | `/messages/{chat_id}`         | Get message history (paginated) |
| POST   | `/messages/{message_id}/star` | Star/unstar a message           |
| GET    | `/messages/starred`           | List starred messages           |
| GET    | `/messages/search?q=text`     | Search messages (full‑text)     |

### Media (`/media`)

| Method | Endpoint                     | Description               |
| ------ | ---------------------------- | ------------------------- |
| POST   | `/media/upload`              | Upload a file (multipart) |
| GET    | `/media/{id}`                | Download or stream media  |
| GET    | `/media/{id}?thumbnail=true` | Get thumbnail             |

### Status (`/status`)

| Method | Endpoint             | Description                  |
| ------ | -------------------- | ---------------------------- |
| POST   | `/status`            | Create a status (text/media) |
| GET    | `/status`            | Get visible statuses         |
| POST   | `/status/{id}/view`  | Mark as viewed               |
| GET    | `/status/{id}/views` | List viewers (author only)   |

### Groups (`/groups`)

| Method | Endpoint                                         | Description              |
| ------ | ------------------------------------------------ | ------------------------ |
| POST   | `/groups`                                        | Create a group           |
| GET    | `/groups/{group_id}`                             | Get group details        |
| PATCH  | `/groups/{group_id}`                             | Update group name/avatar |
| POST   | `/groups/{group_id}/participants`                | Add member (admin only)  |
| DELETE | `/groups/{group_id}/participants/{user_id}`      | Remove member            |
| PATCH  | `/groups/{group_id}/participants/{user_id}/role` | Change role (admin only) |
| GET    | `/groups/{group_id}/participants`                | List participants        |

### Calls (`/calls`)

| Method | Endpoint                  | Description                 |
| ------ | ------------------------- | --------------------------- |
| GET    | `/calls/turn-credentials` | Get TURN server credentials |
| GET    | `/calls/history`          | Get call history            |

### Backup (`/backup`)

| Method | Endpoint          | Description               |
| ------ | ----------------- | ------------------------- |
| POST   | `/backup/export`  | Export chat backup        |
| POST   | `/backup/restore` | Upload and restore backup |

### WebSocket

**Endpoint:** `ws://localhost:8000/ws?token=<jwt>`

#### Message Types (Client → Server)

| Type            | Payload                                                                             |
| --------------- | ----------------------------------------------------------------------------------- |
| `message`       | `{ "chat_id": "uuid", "text": "...", "temp_id": "...", "media_id": "..." }`         |
| `read`          | `{ "message_id": "uuid", "chat_id": "uuid" }`                                       |
| `typing`        | `{ "chat_id": "uuid", "is_typing": true/false }`                                    |
| `heartbeat`     | `{}`                                                                                |
| `call_offer`    | `{ "chat_id": "uuid", "call_type": "audio/video", "sdp": "...", "call_id": "..." }` |
| `call_answer`   | `{ "call_id": "uuid", "sdp": "..." }`                                               |
| `ice_candidate` | `{ "call_id": "uuid", "candidate": "...", "sdpMid": "...", "sdpMLineIndex": ... }`  |
| `call_end`      | `{ "call_id": "uuid" }`                                                             |
| `call_reject`   | `{ "call_id": "uuid" }`                                                             |

---

## Project Structure

```
├── alembic/                      # Database migrations
│   └── versions/                 # Generated migration files
├── api/
│   ├── deps.py                   # Dependency injection (auth, DB)
│   └── routes/                   # REST endpoints
│       ├── auth.py
│       ├── backup.py
│       ├── calls.py
│       ├── chats.py
│       ├── groups.py
│       ├── health.py
│       ├── media.py
│       ├── messages.py
│       ├── status.py
│       └── users.py
├── db/
│   ├── models/                   # SQLAlchemy models
│   │   ├── call.py
│   │   ├── chat.py
│   │   ├── media.py
│   │   ├── message.py
│   │   ├── status.py
│   │   └── user.py
│   └── session.py                # Async engine + session factory
├── schemas/                      # Pydantic request/response models
├── services/
│   └── websocket_manager.py      # WebSocket connection manager
├── utils/                        # Helpers
│   ├── backup.py
│   ├── call_manager.py
│   ├── media_processor.py
│   ├── notifications.py
│   ├── presence.py
│   ├── privacy.py
│   ├── security.py
│   └── storage.py
├── celery_worker.py              # Celery app + tasks
├── main.py                       # FastAPI app entrypoint + WebSocket handler
├── seed_data.py                  # Kenyan demo data seeder
├── tests/                        # Unit & integration tests
├── backups/                      # Exported backup files (local storage)
├── media_storage/                # Uploaded media (originals + thumbnails)
├── Dockerfile
├── docker-compose.yml
├── alembic.ini
├── requirements.txt
└── .env.example
```

---

## Configuration

All configuration via environment variables (see `.env.example`):

| Variable                      | Default                                                  | Description                        |
| ----------------------------- | -------------------------------------------------------- | ---------------------------------- |
| `DATABASE_URL`                | `postgresql+asyncpg://postgres:postgres@db:5432/chatapp` | PostgreSQL connection string       |
| `REDIS_URL`                   | `redis://redis:6379/0`                                   | Redis connection string            |
| `JWT_SECRET`                  | (required)                                               | Secret key for JWT signing         |
| `JWT_ALGORITHM`               | `HS256`                                                  | JWT signing algorithm              |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30`                                                     | Access token TTL (minutes)         |
| `REFRESH_TOKEN_EXPIRE_DAYS`   | `7`                                                      | Refresh token TTL (days)           |
| `STORAGE_TYPE`                | `local`                                                  | `local` or `s3`                    |
| `MEDIA_ROOT`                  | `/app/media_storage`                                     | Local media storage path           |
| `BACKUP_ROOT`                 | `/app/backups`                                           | Local backup storage path          |
| `S3_BUCKET`                   | (optional)                                               | S3 bucket name                     |
| `S3_REGION`                   | (optional)                                               | S3 region                          |
| `FIREBASE_CREDENTIALS`        | (optional)                                               | Firebase service account JSON path |
| `MOCK_OTP`                    | `123456`                                                 | Development OTP bypass code        |

---

## Development

### Local setup (without Docker)

```bash
# Create virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run PostgreSQL and Redis (e.g., via Docker)
docker compose up -d db redis

# Run migrations
alembic upgrade head

# Seed demo data
python seed_data.py

# Start the app
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Run tests

```bash
pytest tests/ -v
```

### Create a migration

```bash
# After changing a model:
alembic revision --autogenerate -m "description"

# Apply it:
alembic upgrade head
```

---

## Scaling

This design is **horizontally scalable**:

1. Add a load balancer (HAProxy / Nginx) in front of multiple FastAPI instances.
2. Enable **Redis Pub/Sub** for cross‑instance WebSocket message routing.
3. Scale Celery workers independently for background tasks.
4. Use S3/MinIO for media storage instead of local volumes.
5. Add PostgreSQL read replicas for message history queries.
6. Partition the `messages` table by `chat_id` and timestamp.

For detailed scaling guidance, see [Architecture.md](Architecture.md).

---

## License

MIT
