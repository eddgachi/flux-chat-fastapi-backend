#!/bin/sh
set -e

# Run migrations will be added in Phase 2
# For Phase 1 we just start the server

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload