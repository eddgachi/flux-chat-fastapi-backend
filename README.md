# Flux Chat — Scalable WhatsApp-like Chat Backend

[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791.svg)](https://postgresql.org)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D.svg)](https://redis.io)
[![Celery](https://img.shields.io/badge/Celery-5.3-37814A.svg)](https://docs.celeryq.dev)
[![Docker](https://img.shields.io/badge/Docker-257bd6?logo=docker&logoColor=white)](https://docker.com)
[![Docker Compose](https://img.shields.io/badge/Docker_Compose-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)

A production-ready real-time messaging backend built with **FastAPI**, **WebSockets**, **PostgreSQL**, **Redis**, and **Celery**. Supports private and group messaging, media sharing, voice/video calls, status updates, and more.

---

## Features

### Messaging

- **1-to-1 private chat** with real-time delivery via WebSockets
- **Group chats** with admin roles, participant management, and per-user message delivery tracking
- **Read receipts** (sent → delivered → read)
- **Typing indicators** (live via Redis TTL)
- **Offline message delivery** — pending messages are delivered on reconnect
- **Message history** with cursor-based pagination

### Media & Files

- **Image/video/audio/document uploads** with async thumbnail generation (Pillow + ffmpeg)
- **Local & S3-compatible storage** (configurable)
- **Voice messages**
- `GET /media/{id}` and `GET /media/{id}?thumbnail=true` for serving

### Presence & Status

- **Online/offline presence** via Redis with heartbeat (25s interval, 35s TTL)
- **Last seen** timestamp persisted on disconnect
- **Status (Stories)** — text, image, or video posts that expire after 24 hours
- **Viewer tracking** — see who viewed your status
- **Privacy controls** — \"My Contacts\" or \"Close Friends\"

### Voice & Video Calls

- **WebRTC signalling** over WebSocket (`call_offer`, `call_answer`, `ice_candidate`, `call_end`, `call_reject`)
- **Call state** managed in Redis with TTL
- **TURN credentials** endpoint for production deployment
- **Call history** with duration tracking

### Chat Management

- **Pin/unpin chats** (up to 5)
- **Archive/unarchive chats**
- **Star/unstar messages**
- **Full-text search** across messages in your chats
- **Per-chat mute** (permanent or timed)

### Notifications & Security

- **Push notifications** via Firebase Cloud Messaging (FCM)
- **Block user** — two-way blocking prevents all communication
- **Two-step verification** (TOTP via pyotp)
- **JWT authentication** (access + refresh tokens)
- **OTP-based login** via phone number

### Backup & Restore

- **Export** your chat history as JSON
- **Restore** from backup on a new device (backup encrypted client-side)

---

## Tech Stack

| Component              | Technology              | Purpose                                                          |
| ---------------------- | ----------------------- | ---------------------------------------------------------------- |
| **API Server**         | FastAPI (Uvicorn)       | REST endpoints + WebSocket server                                |
| **Database**           | PostgreSQL 15 (asyncpg) | Persistent storage — users, messages, chats, media metadata      |
| **Cache / Real-time**  | Redis 7                 | Presence, typing indicators, call state, Celery broker & backend |
| **Background Tasks**   | Celery 5.3              | Thumbnail generation, push notifications, expired status cleanup |
| **ORM**                | SQLAlchemy 2.0 (async)  | Database models and queries                                      |
| **Migrations**         | Alembic                 | Schema versioning                                                |
| **Auth**               | python-jose + passlib   | JWT tokens, bcrypt password hashing                              |
| **Media Processing**   | Pillow + ffmpeg         | Thumbnails for images and videos                                 |
| **Push Notifications** | Firebase Admin SDK      | FCM for Android, APNs via FCM for iOS                            |
| **WebRTC**             | browser/client-side     | STUN (Google public), TURN (self-hosted Coturn)                  |
| **Monitoring**         | Prometheus client       | Metrics endpoint (`/metrics`)                                    |

---

## Architecture Overview

```mermaid
flowchart TB
    subgraph Clients["Clients"]
        C1[Mobile App]
        C2[Web App]
    end

    subgraph API["API Layer"]
        LB["Load Balancer<br/>(HAProxy / Nginx)"]
        FA1["FastAPI Instance 1"]
        FA2["FastAPI Instance 2"]
        FA3["FastAPI Instance ..."]
        WS["WebSocket<br/>Connection Manager"]
    end

    subgraph Cache["Cache & Real-time"]
        R[(Redis 7)]
        RP["Pub/Sub<br/>Cross-instance"]
    end

    subgraph Storage["Persistent Storage"]
        PG[(PostgreSQL 15)]
        MEDIA["Media Storage<br/>(Local / S3)"]
    end

    subgraph Workers["Background Workers"]
        CEL["Celery Worker"]
        BEAT["Celery Beat<br/>(Scheduler)"]
    end

    subgraph External["External Services"]
        FCM["Firebase Cloud Messaging"]
        TURN["TURN Server<br/>(Coturn)"]
    end

    C1 -- "WebSocket + REST" --> LB
    C2 -- "WebSocket + REST" --> LB
    LB --> FA1 & FA2 & FA3
    FA1 & FA2 & FA3 --- WS
    FA1 & FA2 & FA3 <--> R
    R --- RP
    FA1 & FA2 & FA3 <--> PG
    FA1 & FA2 & FA3 <--> MEDIA
    FA1 & FA2 & FA3 -.-> CEL
    CEL <--> PG
    CEL <--> MEDIA
    BEAT --> CEL
    CEL -.-> FCM
    WS -.-> TURN

    classDef client fill:#bbdefb,stroke:#1565c0,color:#000000
    classDef api fill:#e1bee7,stroke:#6a1b9a,color:#000000
    classDef cache fill:#ffe0b2,stroke:#e65100,color:#000000
    classDef storage fill:#c8e6c9,stroke:#2e7d32,color:#000000
    classDef worker fill:#f8bbd0,stroke:#c62828,color:#000000
    classDef external fill:#e0e0e0,stroke:#424242,stroke-dasharray: 5 5,color:#000000

    class C1,C2 client
    class FA1,FA2,FA3,WS api
    class R,RP cache
    class PG,MEDIA storage
    class CEL,BEAT worker
    class FCM,TURN external
```

### Data Flow

**1. Authentication** (`POST /auth/verify-otp`) → JWT issued → client stores access + refresh tokens

**2. Real-time messaging** (WebSocket):

- Client connects to `/ws?token=<jwt>`
- FastAPI authenticates, stores WebSocket in Connection Manager (in-memory map)
- Messages stored in PostgreSQL → delivered to recipient via their WebSocket
- If recipient offline → message marked `sent`, delivered on reconnect
- **Cross-instance**: Via Redis Pub/Sub when scaling to multiple FastAPI nodes

**3. Media upload** (`POST /media/upload`):

- File saved to disk/S3 → Celery generates thumbnail → `media_id` returned
- Client sends message referencing `media_id`

**4. Voice/video calls** (WebRTC):

- Signalling via WebSocket (`call_offer`/`call_answer`/`ice_candidate`)
- Media flows peer-to-peer (STUN for NAT traversal, TURN as fallback)
- Call state managed in Redis with 5-minute TTL

**5. Presence**:

- Client sends `heartbeat` every 25s over WebSocket
- Redis `presence:{user_id}` set with 35s TTL
- On disconnect, `last_seen` updated in PostgreSQL

### Key Design Decisions:

- **Single-instance first** — works out of the box with `docker-compose up`
- **Redis Pub/Sub** for cross-instance message routing when scaling horizontally
- **Async everywhere** — FastAPI async endpoints, async SQLAlchemy, async Redis
- **Celery** for non-real-time background tasks only (media processing, push notifications, cleanup)

---

## Quick Start

### Prerequisites

- Docker & Docker Compose (v2+)
- Python 3.11+ (optional, for local development)

### Run with Docker (recommended)

```bash
# Clone and enter the project
git clone <repo-url> flux-chat
cd flux-chat

# Copy environment variables
cp .env.example .env

# Start all services
docker compose up -d --build

# Check logs
docker compose logs -f app
```

The app will be available at **http://localhost:8000**.

| Service     | Port | URL                        |
| ----------- | ---- | -------------------------- |
| FastAPI App | 8000 | http://localhost:8000      |
| API Docs    | 8000 | http://localhost:8000/docs |
| PostgreSQL  | 5432 | localhost:5432             |
| Redis       | 6379 | localhost:6379             |

### First-time setup

On first run, the app automatically:

1. Runs database migrations (`alembic upgrade head`)
2. Seeds **Kenyan demo data** — 8 users with private chats and group conversations

### Demo Users

| Name              | Phone Number  |
| ----------------- | ------------- |
| Wanjiku Kamau     | +254712345678 |
| Omondi Otieno     | +254723456789 |
| Achieng' Nyambura | +254734567890 |
| Kiprop Chebet     | +254745678901 |
| Mwende Mutua      | +254756789012 |
| Barasa Wekesa     | +254767890123 |
| Nyokabi Maina     | +254778901234 |
| Juma Mwangi       | +254789012345 |

> **Note:** Seed data is only created when the database is empty. To re-seed, run `docker compose down -v && docker compose up -d`.

---

## API Endpoints

### Authentication (`/auth`)

| Method | Endpoint            | Description                  |
| ------ | ------------------- | ---------------------------- |
| POST   | `/auth/request-otp` | Request OTP for phone number |
| POST   | `/auth/verify-otp`  | Verify OTP and get tokens    |
| POST   | `/auth/refresh`     | Refresh access token         |
| POST   | `/auth/2fa/enable`  | Enable two-step verification |
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
| GET    | `/chats`                   | List user's chats (with last message) |
| POST   | `/chats/private/{user_id}` | Create or get private chat            |
| PATCH  | `/chats/{chat_id}/pin`     | Pin/unpin chat                        |
| PATCH  | `/chats/{chat_id}/archive` | Archive/unarchive                     |
| PATCH  | `/chats/{chat_id}/mute`    | Mute/unmute chat                      |

### Messages (`/messages`)

| Method | Endpoint                  | Description                            |
| ------ | ------------------------- | -------------------------------------- |
| GET    | `/messages/{chat_id}`     | Get message history (cursor paginated) |
| POST   | `/messages/{id}/star`     | Star/unstar a message                  |
| GET    | `/messages/starred`       | List starred messages                  |
| GET    | `/messages/search?q=text` | Search messages                        |

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

| Endpoint                             | Description                    |
| ------------------------------------ | ------------------------------ |
| `ws://localhost:8000/ws?token=<jwt>` | Real-time messaging connection |

#### WebSocket Message Types

| Type            | Direction       | Payload                                           |
| --------------- | --------------- | ------------------------------------------------- |
| `message`       | Client → Server | `{ chat_id, text, temp_id, media_id? }`           |
| `read`          | Client → Server | `{ message_id, chat_id }`                         |
| `typing`        | Client → Server | `{ chat_id, is_typing }`                          |
| `heartbeat`     | Client → Server | `{}`                                              |
| `call_offer`    | Client → Server | `{ chat_id, call_type, sdp, call_id? }`           |
| `call_answer`   | Client → Server | `{ call_id, sdp }`                                |
| `ice_candidate` | Client → Server | `{ call_id, candidate, sdpMid?, sdpMLineIndex? }` |
| `call_end`      | Client → Server | `{ call_id }`                                     |
| `call_reject`   | Client → Server | `{ call_id }`                                     |

---

## Project Structure

```
├── api/                      # FastAPI application
│   ├── routes/               # Endpoint handlers
│   │   ├── auth.py           # Authentication
│   │   ├── users.py          # User profile
│   │   ├── chats.py          # Chat management
│   │   ├── messages.py       # Messages, search, starring
│   │   ├── media.py          # File upload & serving
│   │   ├── status.py         # Stories
│   │   ├── calls.py          # Call history & TURN credentials
│   │   ├── groups.py         # Group management
│   │   ├── backup.py         # Export & restore
│   │   └── health.py         # Health check & metrics
│   └── deps.py               # Dependencies (auth, DB)
│
├── db/                       # Database layer
│   ├── models/               # SQLAlchemy models
│   │   ├── user.py           # User, UserSession, UserDevice, BlockedUser
│   │   ├── chat.py           # Chat, ChatParticipant
│   │   ├── message.py        # Message, MessageDelivery, StarredMessage
│   │   ├── media.py          # Media
│   │   ├── status.py         # Status, StatusView
│   │   └── call.py           # Call
│   └── session.py            # Async engine + session factory
│
├── schemas/                  # Pydantic request/response models
├── services/                 # Business logic
│   └── websocket_manager.py  # WebSocket connection manager
│
├── utils/                    # Utilities
│   ├── security.py           # JWT encode/decode
│   ├── presence.py           # Redis presence helpers
│   ├── call_manager.py       # Redis call state helpers
│   ├── media_processor.py    # File validation
│   ├── backup.py             # Backup data collection
│   └── privacy.py            # Status privacy checks
│
├── celery_worker.py          # Celery app + tasks (media, cleanup)
├── main.py                   # FastAPI app + WebSocket handler
├── seed_data.py              # Kenyan demo data seeder
├── Dockerfile                # Container image
├── docker-compose.yml        # Multi-service orchestration
├── alembic/                  # Database migrations
└── requirements.txt          # Python dependencies
```

---

## Configuration

All configuration is via environment variables (see `.env.example`):

| Variable               | Default                                                        | Description                        |
| ---------------------- | -------------------------------------------------------------- | ---------------------------------- |
| `DATABASE_URL`         | `postgresql+asyncpg://postgres:postgres@localhost:5432/chatdb` | PostgreSQL connection string       |
| `REDIS_URL`            | `redis://redis:6379/0`                                         | Redis connection string            |
| `JWT_SECRET`           | (required)                                                     | Secret key for JWT signing         |
| `JWT_ALGORITHM`        | `HS256`                                                        | JWT signing algorithm              |
| `ACCESS_TOKEN_EXPIRE`  | `15`                                                           | Access token TTL (minutes)         |
| `REFRESH_TOKEN_EXPIRE` | `7`                                                            | Refresh token TTL (days)           |
| `STORAGE_TYPE`         | `local`                                                        | `local` or `s3`                    |
| `MEDIA_ROOT`           | `/app/media_storage`                                           | Local media storage path           |
| `S3_BUCKET`            | (optional)                                                     | S3 bucket name                     |
| `S3_REGION`            | (optional)                                                     | S3 region                          |
| `FIREBASE_CREDENTIALS` | (optional)                                                     | Firebase service account JSON path |
| `COTURN_SECRET`        | (optional)                                                     | Coturn shared secret for TURN auth |

---

## Development

### Local setup (without Docker)

```bash
# Create virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run PostgreSQL and Redis (you need them running locally)
# or use Docker for just the services:
docker compose up -d db redis

# Run migrations
alembic upgrade head

# Seed demo data
python3 seed_data.py

# Start the app
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Run tests

```bash
pytest tests/ -v
```

### Creating migrations

```bash
# After changing models, auto-generate a migration:
alembic revision --autogenerate -m "description"

# Apply it:
alembic upgrade head
```

---

## Scaling

This design is **horizontally scalable**:

1. **Add a load balancer** (HAProxy / Nginx) in front of multiple FastAPI instances
2. **Enable Redis Pub/Sub** for cross-instance WebSocket message routing
3. **Scale Celery workers** independently for background tasks
4. **Use S3/MinIO** for media storage instead of local volumes
5. **Add PostgreSQL read replicas** for message history queries
6. **Partition messages table** by `chat_id` and timestamp

For detailed scaling guidance, see [Architecture.md](Architecture.md).

---

## License

MIT
"
