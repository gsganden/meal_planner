from httpx import AsyncClient, ASGITransport

from meal_planner.main import app
import pytest


@pytest.mark.anyio
async def test_smoke_root(anyio_backend):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
    assert response.status_code == 200


@pytest.mark.anyio
async def test_smoke_extract_recipe(anyio_backend):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/recipes/extract")
    assert response.status_code == 200
