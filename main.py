from fastapi import FastAPI

from api.routes import auth, health, users

app = FastAPI(title="Chat App Backend", version="0.1.0")

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(health.router)


@app.get("/")
async def root():
    return {"message": "Welcome to Flux Chat API"}
