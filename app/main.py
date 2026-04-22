from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1 import auth, chats, health
from app.api.v1.websocket import websocket_endpoint
from app.core.config import settings
from app.core.connection_manager import manager
from app.core.redis_listener import redis_listener
from app.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: nothing special needed (engine already created)
    print("Starting up...")
    await manager.initialize_redis()  # Initialize Redis publisher
    await redis_listener.start()
    yield
    # Shutdown: dispose DB connections
    await redis_listener.stop()  # Stop Redis listener
    await manager.close_redis()  # Close Redis publisher
    await engine.dispose()
    print("Shutting down...")


def create_application() -> FastAPI:
    app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG, lifespan=lifespan)

    app.include_router(health.router, prefix="/api/v1", tags=["health"])
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(chats.router, prefix="/api/v1")

    # WebSocket endpoint
    app.add_api_websocket_route("/ws/{chat_id}", websocket_endpoint)

    @app.get("/")
    async def root():
        return {"message": f"Welcome to {settings.APP_NAME}"}

    return app


app = create_application()
