from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1 import auth, chats, health
from app.core.config import settings
from app.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: nothing special needed (engine already created)
    print("Starting up...")
    yield
    # Shutdown: dispose DB connections
    await engine.dispose()
    print("Shutting down...")


def create_application() -> FastAPI:
    app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG, lifespan=lifespan)

    app.include_router(health.router, prefix="/api/v1", tags=["health"])
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(chats.router, prefix="/api/v1")

    @app.get("/")
    async def root():
        return {"message": f"Welcome to {settings.APP_NAME}"}

    return app


app = create_application()
