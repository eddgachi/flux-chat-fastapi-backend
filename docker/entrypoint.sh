#!/bin/sh
set -e

echo "Running database migrations..."
alembic upgrade head

# Use --reload only in development (set RELOAD=true in docker-compose dev override)
if [ "${RELOAD:-false}" = "true" ]; then
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
else
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
fi
