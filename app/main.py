from fastapi import FastAPI

from app.api.v1 import health
from app.core.config import settings


def create_application() -> FastAPI:
    app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG)

    # Include routers
    app.include_router(health.router, prefix="/api/v1", tags=["health"])

    @app.get("/")
    async def root():
        return {"message": f"Welcome to {settings.APP_NAME}"}

    return app


app = create_application()
