from fastapi import FastAPI
from api.routes import auth, users, health

app = FastAPI(title="Flux Chat API", version="0.1.0")

app.include_router(health.router, tags=["health"])
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(users.router, prefix="/users", tags=["users"])

@app.get("/")
async def root():
    return {"message": "Welcome to Flux Chat API"}
