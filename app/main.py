import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1 import auth, chats, health, messages, users
from app.api.v1.websocket import websocket_endpoint
from app.core.config import settings
from app.core.connection_manager import manager
from app.core.metrics import metrics_endpoint
from app.core.redis_listener import redis_listener
from app.db.session import engine
from app.middleware.metrics import MetricsMiddleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up %s...", settings.APP_NAME)
    await manager.initialize_redis()
    await redis_listener.start()
    yield
    logger.info("Shutting down...")
    await redis_listener.stop()
    await manager.close_redis()
    await engine.dispose()


def create_application() -> FastAPI:
    app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG, lifespan=lifespan)

    # Add metrics middleware
    app.add_middleware(MetricsMiddleware)

    # Include REST routers
    app.include_router(health.router, prefix="/api/v1", tags=["health"])
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(chats.router, prefix="/api/v1")
    app.include_router(messages.router, prefix="/api/v1")
    app.include_router(users.router, prefix="/api/v1")

    # Metrics endpoint for Prometheus
    app.add_api_route("/metrics", metrics_endpoint, tags=["metrics"])

    # WebSocket endpoint
    app.add_api_websocket_route("/ws/{chat_id}", websocket_endpoint)

    @app.get("/")
    async def root():
        return {"message": f"Welcome to {settings.APP_NAME}"}

    return app


app = create_application()
