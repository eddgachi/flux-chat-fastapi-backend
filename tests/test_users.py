import pytest
from httpx import AsyncClient

from main import app


@pytest.mark.asyncio
async def test_read_user_me_unauthorized():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/users/me")
    assert response.status_code == 401
