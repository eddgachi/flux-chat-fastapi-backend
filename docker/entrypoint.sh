#!/bin/sh
set -e

# Wait for postgres to be ready (optional, but docker-compose healthcheck already ensures)
echo "Running database migrations..."
alembic upgrade head

# Start the FastAPI app
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload