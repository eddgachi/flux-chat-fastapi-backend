# Flux Chat — FastAPI Backend

A production-oriented real-time chat API built with FastAPI, PostgreSQL, Redis, and Celery. Supports WebSocket messaging with pub/sub fan-out across multiple server instances, background notifications, and full observability via Prometheus and Grafana.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Tech Stack](#tech-stack)
- [Features](#features)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Environment Variables](#environment-variables)
  - [Running with Docker](#running-with-docker)
  - [Running Locally (without Docker)](#running-locally-without-docker)
- [Database Migrations](#database-migrations)
- [API Reference](#api-reference)
  - [Authentication](#authentication)
  - [Chats](#chats)
  - [Messages](#messages)
  - [Users](#users)
  - [WebSocket](#websocket)
  - [Health & Metrics](#health--metrics)
- [WebSocket Protocol](#websocket-protocol)
- [Monitoring](#monitoring)
- [Background Tasks (Celery)](#background-tasks-celery)
- [Useful Commands](#useful-commands)

---

## Architecture Overview

```
Client (Browser / App)
       │
       │  HTTP / WebSocket
       ▼
┌─────────────────────────────────┐
│         FastAPI App             │
│  ┌──────────┐  ┌─────────────┐ │
│  │ REST API │  │  WebSocket  │ │
│  └────┬─────┘  └──────┬──────┘ │
│       │               │        │
│  ┌────▼───────────────▼──────┐ │
│  │     Connection Manager    │ │
│  │  (in-memory WS registry)  │ │
│  └──────────────┬────────────┘ │
└─────────────────┼──────────────┘
                  │ publish / subscribe
          ┌───────▼────────┐
          │     Redis      │◄─── Celery Broker
          │  (Pub/Sub +    │
          │   Presence)    │
          └───────┬────────┘
                  │ fan-out to all instances
          ┌───────▼────────┐
          │ Redis Listener │ (background asyncio task)
          │  broadcasts to │
          │ local WS conns │
          └────────────────┘

┌──────────────┐    ┌────────────────┐    ┌───────────────┐
│  PostgreSQL  │    │ Celery Worker  │    │  Prometheus   │
│  (messages,  │    │ (push notifs,  │    │  + Grafana    │
│  users, etc) │    │  analytics)    │    │  (metrics)    │
└──────────────┘    └────────────────┘    └───────────────┘
```

**Message delivery flow:**
1. Client sends `send_message` over WebSocket.
2. Server saves the message to PostgreSQL.
3. Server publishes the message to a Redis channel (`chat:{id}`).
4. The `RedisMessageListener` (running on every app instance) receives the event and forwards it to all locally connected WebSocket clients in that chat.
5. Celery tasks fire asynchronously for push notifications and analytics.

This design scales horizontally — adding more app instances only requires they all share the same Redis.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Web framework | FastAPI 0.115 + Uvicorn |
| Database | PostgreSQL 15 (async via `asyncpg` + SQLAlchemy 2.0) |
| Migrations | Alembic |
| Real-time | WebSockets + Redis pub/sub |
| Presence | Redis (TTL-based keys) |
| Background jobs | Celery 5 (broker: Redis) |
| Auth | JWT (`python-jose`) + bcrypt passwords |
| Monitoring | Prometheus client + Grafana |
| Containerisation | Docker + Docker Compose |

---

## Features

- **Authentication** — Register and login with JWT access tokens; password hashing with bcrypt.
- **1-to-1 and group chats** — Create private chats or named group chats; manage participants.
- **Real-time messaging** — WebSocket-based with Redis pub/sub fan-out; works across multiple server instances.
- **Message editing** — Edit your own messages; an `edited_at` timestamp is set and broadcast to participants.
- **Soft delete** — Delete a message (content is cleared, slot is retained) with a broadcast event.
- **Read receipts** — Mark messages as read (idempotent); broadcasts a `read_receipt` event. Unread counts per chat available via REST.
- **Typing indicators** — Lightweight `typing_start` / `typing_stop` events over WebSocket; no database writes required.
- **User presence** — Redis TTL-based online/offline tracking. `user_online` / `user_offline` events broadcast on connect/disconnect. Clients send `ping` heartbeats to stay online.
- **Message history** — Cursor-based pagination (`before=<message_id>`) for efficient loading of older messages without slow SQL `OFFSET`.
- **Message search** — Case-insensitive full-text search within a chat.
- **User search** — Find other users by username prefix to start new chats.
- **Background notifications** — Celery tasks simulate push notifications (FCM/APNs stub) and analytics updates.
- **Observability** — Prometheus metrics (HTTP latency/throughput, WebSocket connections, messages, Celery tasks) exposed at `/metrics`; Grafana dashboard provisioned automatically.
- **Health check** — `/api/v1/health` reports database and Celery worker status.

---

## Project Structure

```
flux-chat-fastapi-backend/
├── app/
│   ├── api/v1/
│   │   ├── auth.py          # Register, login, /me
│   │   ├── chats.py         # CRUD chats, participants, offset-paginated messages
│   │   ├── messages.py      # Edit, delete, read receipts, search, cursor pagination
│   │   ├── users.py         # User search, presence bulk-check
│   │   ├── websocket.py     # WebSocket endpoint + message dispatch
│   │   └── health.py        # Health check
│   ├── core/
│   │   ├── config.py        # Pydantic settings (reads .env)
│   │   ├── connection_manager.py  # In-memory WS registry + Redis publisher
│   │   ├── dependencies.py  # get_current_user FastAPI dependency
│   │   ├── metrics.py       # Prometheus counters/histograms/gauges
│   │   ├── redis_listener.py      # Background pub/sub consumer
│   │   └── security.py      # JWT encode/decode, bcrypt helpers
│   ├── db/
│   │   ├── models/
│   │   │   ├── user.py
│   │   │   ├── chat.py
│   │   │   ├── chat_participant.py
│   │   │   ├── message.py
│   │   │   └── message_read.py
│   │   ├── base.py          # Declarative base
│   │   └── session.py       # Async engine + session factory
│   ├── middleware/
│   │   └── metrics.py       # HTTP metrics middleware
│   ├── schemas/             # Pydantic request/response models
│   ├── services/
│   │   ├── chat_service.py
│   │   ├── message_service.py
│   │   ├── presence_service.py    # Redis presence helpers
│   │   ├── user_service.py
│   │   └── websocket_service.py   # Save + publish on message send
│   ├── tasks/
│   │   └── notifications.py # Celery tasks
│   ├── celery_app.py
│   └── main.py
├── alembic/
│   └── versions/            # Migration files
├── docker/
│   ├── Dockerfile
│   ├── Dockerfile.celery
│   ├── entrypoint.sh        # Runs migrations then starts uvicorn
│   ├── entrypoint-celery.sh
│   ├── grafana/             # Auto-provisioned datasource + dashboards
│   └── prometheus/
│       └── prometheus.yml
├── .dockerignore
├── .env                     # Local secrets (not committed)
├── docker-compose.yml
├── requirements.txt
└── alembic.ini
```

---

## Getting Started

### Prerequisites

- Docker 24+ and Docker Compose v2
- Or, for local dev: Python 3.12, PostgreSQL 15, Redis 7

### Environment Variables

Copy the example below into a `.env` file at the project root:

```env
# Database
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=chatdb

# App
SECRET_KEY=your-secret-key-change-in-production
DEBUG=true

# Monitoring (optional — set before starting Docker)
GRAFANA_USER=admin
GRAFANA_PASSWORD=admin
```

`DATABASE_URL` and `REDIS_URL` are automatically set by Docker Compose. When running locally, set them in `.env`:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/chatdb
REDIS_URL=redis://localhost:6379/0
```

### Running with Docker

```bash
# Build and start all services
docker compose up --build

# Start in detached mode
docker compose up -d --build

# Rebuild only the app after a code change
docker compose up --build app

# Tear down everything (keeps volumes)
docker compose down

# Tear down and wipe all data
docker compose down -v
```

Services started:

| Service | Port | Description |
|---|---|---|
| `app` | 8000 | FastAPI application |
| `postgres` | 5432 | PostgreSQL database |
| `redis` | 6379 | Redis (pub/sub + Celery broker) |
| `celery-worker` | — | Background task worker |
| `prometheus` | 9090 | Metrics scraper |
| `grafana` | 3000 | Dashboards (login: admin / admin) |

Migrations run automatically on container start via `entrypoint.sh`.

> **Hot reload in development:** The app container sets `RELOAD=true` automatically. Remove or set it to `false` in `docker-compose.yml` for production-like behaviour.

### Running Locally (without Docker)

```bash
# 1. Create and activate virtualenv
python3.12 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start PostgreSQL and Redis (e.g. via Homebrew or system packages)

# 4. Set environment variables
cp .env.example .env   # edit with your local values

# 5. Run migrations
alembic upgrade head

# 6. Start the app
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 7. Start a Celery worker (separate terminal)
celery -A app.celery_app worker --loglevel=info --concurrency=2
```

---

## Database Migrations

```bash
# Apply all pending migrations
docker compose exec app alembic upgrade head

# Create a new migration after changing a model
docker compose exec app alembic revision --autogenerate -m "describe your change"

# Downgrade one step
docker compose exec app alembic downgrade -1

# View migration history
docker compose exec app alembic history

# Inspect the database directly
docker compose exec postgres psql -U postgres -d chatdb

# List tables
docker compose exec postgres psql -U postgres -d chatdb -c "\dt"

# Check users
docker compose exec postgres psql -U postgres -d chatdb -c "SELECT id, username, email FROM users;"
```

### Migration history

| Revision | Description |
|---|---|
| `6c93d0c0dead` | Initial schema: users, chats, chat_participants, messages |
| `a1b2c3d4e5f6` | Add `is_deleted` + `edited_at` to messages; `last_seen_at` to users; `message_reads` table |

---

## API Reference

Interactive docs are available at [http://localhost:8000/docs](http://localhost:8000/docs) (Swagger UI) and [http://localhost:8000/redoc](http://localhost:8000/redoc).

All protected endpoints require a `Bearer` token in the `Authorization` header.

### Authentication

#### Register

```http
POST /api/v1/auth/register
Content-Type: application/json

{
  "username": "alice",
  "email": "alice@example.com",
  "password": "supersecret"
}
```

#### Login

```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "username_or_email": "alice",
  "password": "supersecret"
}
```

Response:
```json
{ "access_token": "<jwt>", "token_type": "bearer" }
```

#### Get current user

```http
GET /api/v1/auth/me
Authorization: Bearer <token>
```

---

### Chats

#### Create a chat

```http
POST /api/v1/chats/
Authorization: Bearer <token>
Content-Type: application/json

# 1-to-1 chat
{ "participant_ids": [2] }

# Group chat
{ "is_group": true, "title": "Team Alpha", "participant_ids": [2, 3, 4] }
```

#### List your chats

```http
GET /api/v1/chats/?skip=0&limit=50
Authorization: Bearer <token>
```

Returns chats with a `last_message_preview` and `last_message_time` for rendering a chat list.

#### Get messages (offset pagination)

```http
GET /api/v1/chats/{chat_id}/messages?skip=0&limit=50
Authorization: Bearer <token>
```

#### Add participant

```http
POST /api/v1/chats/{chat_id}/participants
Authorization: Bearer <token>
Content-Type: application/json

{ "user_id": 5 }
```

#### Remove participant

```http
DELETE /api/v1/chats/{chat_id}/participants/{user_id}
Authorization: Bearer <token>
```

---

### Messages

#### Load history (cursor pagination) — preferred for infinite scroll

```http
GET /api/v1/chats/{chat_id}/messages/history?limit=50
GET /api/v1/chats/{chat_id}/messages/history?before=142&limit=50
Authorization: Bearer <token>
```

Pass `next_cursor` from the previous response as `before` in the next request. More efficient than offset pagination as chat history grows.

Response:
```json
{
  "messages": [...],
  "next_cursor": 92,
  "has_more": true
}
```

#### Search messages

```http
GET /api/v1/chats/{chat_id}/messages/search?q=hello&limit=20
Authorization: Bearer <token>
```

#### Unread count

```http
GET /api/v1/chats/{chat_id}/unread
Authorization: Bearer <token>
```

Response: `{ "chat_id": 1, "unread_count": 7 }`

#### Edit a message

```http
PATCH /api/v1/chats/{chat_id}/messages/{message_id}
Authorization: Bearer <token>
Content-Type: application/json

{ "content": "Updated text" }
```

Broadcasts a `message_updated` WebSocket event to all participants. Only the sender can edit.

#### Delete a message

```http
DELETE /api/v1/chats/{chat_id}/messages/{message_id}
Authorization: Bearer <token>
```

Soft-deletes the message (content is cleared, record is retained). Broadcasts `message_deleted`. Only the sender can delete.

#### Mark as read

```http
POST /api/v1/chats/{chat_id}/messages/{message_id}/read
Authorization: Bearer <token>
```

Idempotent — safe to call multiple times. Broadcasts a `read_receipt` event.

---

### Users

#### Search users (by username prefix)

```http
GET /api/v1/users/search?q=ali&limit=10
Authorization: Bearer <token>
```

Useful for the "new chat" user picker.

#### Bulk presence check

```http
GET /api/v1/users/presence?user_ids=1,2,3
Authorization: Bearer <token>
```

Uses a Redis pipeline for a single round-trip regardless of how many user IDs are queried.

Response:
```json
[
  { "user_id": 1, "is_online": true,  "last_seen_at": null },
  { "user_id": 2, "is_online": false, "last_seen_at": "2026-04-22T09:00:00" },
  { "user_id": 3, "is_online": true,  "last_seen_at": null }
]
```

---

### WebSocket

```
ws://localhost:8000/ws/{chat_id}?token=<jwt>
```

Authentication happens before the connection is accepted. The connection is rejected with code `1008` if the token is invalid or the user is not a participant in the requested chat.

See the [WebSocket Protocol](#websocket-protocol) section below for full message type documentation.

**Quick start with wscat:**

```bash
# Install wscat
npm install -g wscat

# Connect (replace TOKEN with the value from /login)
wscat -c "ws://localhost:8000/ws/1?token=TOKEN"

# Send a message
> {"type": "send_message", "data": {"content": "Hello!"}}

# Typing indicator
> {"type": "typing_start", "data": {}}
> {"type": "typing_stop", "data": {}}

# Heartbeat (keeps presence alive)
> {"type": "ping", "data": {}}

# Mark a message as read
> {"type": "mark_read", "data": {"message_id": 42}}
```

---

### Health & Metrics

```http
GET /api/v1/health
```

```json
{ "status": "ok", "database": "ok", "celery": "ok" }
```

```http
GET /metrics
```

Prometheus text-format metrics for scraping.

---

## WebSocket Protocol

All messages are JSON with a `type` field and a `data` object.

### Client → Server

| `type` | `data` fields | Description |
|---|---|---|
| `send_message` | `content: string` | Send a new chat message |
| `typing_start` | _(none)_ | Notify others you started typing |
| `typing_stop` | _(none)_ | Notify others you stopped typing |
| `ping` | _(none)_ | Heartbeat — refreshes your presence TTL (60 s); server replies with `pong` |
| `mark_read` | `message_id: int` | Mark a specific message as read |

### Server → Client

| `type` | `data` fields | Trigger |
|---|---|---|
| `connection_established` | `chat_id`, `user_id`, `username` | Sent once on successful connection |
| `new_message` | `id`, `chat_id`, `sender_id`, `sender_name`, `content`, `sent_at`, `updated_at` | A new message was sent |
| `message_updated` | `id`, `chat_id`, `content`, `edited_at` | A message was edited |
| `message_deleted` | `id`, `chat_id` | A message was soft-deleted |
| `read_receipt` | `message_id`, `user_id`, `read_at` | A participant read a message |
| `typing_start` | `user_id`, `username` | A participant started typing |
| `typing_stop` | `user_id`, `username` | A participant stopped typing |
| `user_online` | `user_id`, `username` | A participant connected to this chat |
| `user_offline` | `user_id`, `username` | A participant disconnected from all chats |
| `pong` | _(empty)_ | Reply to a `ping` |
| `error` | `message: string` | Something went wrong with the last client message |

---

## Monitoring

Grafana is available at [http://localhost:3000](http://localhost:3000) (default credentials: `admin` / `admin`, overridable via `GRAFANA_USER` / `GRAFANA_PASSWORD` in `.env`).

The Prometheus datasource is auto-provisioned. Dashboards placed in `docker/grafana/dashboards/` are loaded automatically.

### Tracked metrics

| Metric | Type | Labels |
|---|---|---|
| `http_requests_total` | Counter | `method`, `endpoint`, `status` |
| `http_request_duration_seconds` | Histogram | `method`, `endpoint` |
| `websocket_connections_total` | Counter | `chat_id` |
| `websocket_connections_active` | Gauge | `chat_id` |
| `websocket_messages_received_total` | Counter | `chat_id` |
| `websocket_messages_sent_total` | Counter | `chat_id` |
| `messages_sent_total` | Counter | `chat_id`, `is_group` |
| `active_chats_gauge` | Gauge | — |
| `celery_tasks_total` | Counter | `task_name`, `status` |
| `celery_task_duration_seconds` | Histogram | `task_name` |

Prometheus scrapes `/metrics` on the `app` service every 10 seconds.

---

## Background Tasks (Celery)

The Celery worker runs separately from the app. Redis is used as the broker.

| Task | Trigger | Behaviour |
|---|---|---|
| `send_push_notification` | After each message sent | Stub for FCM/APNs; rate-limited to 10/min; retries 3× on failure |
| `send_email_notification` | (Available, not wired by default) | Stub for SMTP; retries 2× |
| `update_message_analytics` | After each message sent | Stub for analytics counters; no retry (non-critical) |

```bash
# View active Celery tasks
docker exec -it flux-chat-fastapi-backend-celery-worker-1 \
  celery -A app.celery_app inspect active

# View registered tasks
docker exec -it flux-chat-fastapi-backend-celery-worker-1 \
  celery -A app.celery_app inspect registered

# Follow worker logs
docker compose logs -f celery-worker
```

---

## Useful Commands

```bash
# --- Docker ---
docker compose up --build              # Build and start everything
docker compose up -d                   # Start in background
docker compose down -v                 # Stop and remove volumes
docker compose restart app             # Restart only the app
docker compose logs -f app             # Follow app logs
docker compose logs -f celery-worker   # Follow worker logs

# --- Database ---
docker compose exec app alembic upgrade head
docker compose exec app alembic revision --autogenerate -m "your message"
docker compose exec postgres psql -U postgres -d chatdb

# --- Manual testing ---
# 1. Register a user
curl -s -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","email":"alice@example.com","password":"secret123"}' | jq .

# 2. Login and capture token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username_or_email":"alice","password":"secret123"}' | jq -r .access_token)

# 3. Create a chat
curl -s -X POST http://localhost:8000/api/v1/chats/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"participant_ids":[2]}' | jq .

# 4. Connect via WebSocket
wscat -c "ws://localhost:8000/ws/1?token=$TOKEN"

# 5. Send a burst of messages (stress test)
for i in {1..10}; do
  echo '{"type":"send_message","data":{"content":"Message '$i'"}}' \
    | wscat -c "ws://localhost:8000/ws/1?token=$TOKEN"
done

# --- Misc ---
chmod +x docker/entrypoint.sh          # Fix entrypoint permissions if needed
```
