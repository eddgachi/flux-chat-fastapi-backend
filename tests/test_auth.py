import pytest
from httpx import AsyncClient

from main import app


@pytest.mark.asyncio
async def test_login_dummy():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post(
            "/auth/login", data={"username": "testuser", "password": "testpassword"}
        )
    assert response.status_code == 200
    assert "access_token" in response.json()
