#!/bin/sh
set -e

# Wait for Redis to be ready
echo "Waiting for Redis..."
while ! nc -z redis 6379; do
  sleep 1
done
echo "Redis is ready"

# Start Celery worker
# -A: application, -l: log level, -c: concurrency (number of worker processes)
exec celery -A app.celery_app worker \
  --loglevel=info \
  --concurrency=2 \
  --hostname=worker@%h