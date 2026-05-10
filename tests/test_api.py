"""Tests for model API endpoints."""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from evalarena.app import create_app
from evalarena.db.database import init_db, close_db


@pytest_asyncio.fixture
async def app(tmp_path):
    """Create test app with temporary database."""
    db_path = tmp_path / "test.db"
    await init_db(db_path)
    app = create_app()
    yield app
    await close_db()


@pytest_asyncio.fixture
async def client(app):
    """Create test HTTP client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestModelAPI:
    """Tests for /api/models endpoints."""

    async def test_create_model(self, client):
        """Should create a model and return 201."""
        resp = await client.post("/api/models", json={
            "name": "gpt-4o",
            "organization": "OpenAI",
            "description": "GPT-4 Omni",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "gpt-4o"
        assert data["organization"] == "OpenAI"
        assert data["elo_rating"] == 1000.0
        assert data["id"] is not None

    async def test_create_model_duplicate(self, client):
        """Should return 409 on duplicate name."""
        await client.post("/api/models", json={"name": "gpt-4o"})
        resp = await client.post("/api/models", json={"name": "gpt-4o"})
        assert resp.status_code == 409

    async def test_create_model_validation(self, client):
        """Should return 422 on invalid input."""
        resp = await client.post("/api/models", json={"name": ""})
        assert resp.status_code == 422

    async def test_list_models(self, client):
        """Should list models ordered by ELO."""
        await client.post("/api/models", json={"name": "model-a", "initial_elo": 1200})
        await client.post("/api/models", json={"name": "model-b", "initial_elo": 900})
        resp = await client.get("/api/models")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["name"] == "model-a"
        assert data[1]["name"] == "model-b"

    async def test_get_model(self, client):
        """Should get a model by ID."""
        create_resp = await client.post("/api/models", json={"name": "test-model"})
        model_id = create_resp.json()["id"]
        resp = await client.get(f"/api/models/{model_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "test-model"

    async def test_get_model_not_found(self, client):
        """Should return 404 for non-existent model."""
        resp = await client.get("/api/models/999")
        assert resp.status_code == 404

    async def test_delete_model(self, client):
        """Should delete a model."""
        create_resp = await client.post("/api/models", json={"name": "doomed"})
        model_id = create_resp.json()["id"]
        resp = await client.delete(f"/api/models/{model_id}")
        assert resp.status_code == 204
        resp = await client.get(f"/api/models/{model_id}")
        assert resp.status_code == 404

    async def test_delete_model_not_found(self, client):
        """Should return 404 when deleting non-existent model."""
        resp = await client.delete("/api/models/999")
        assert resp.status_code == 404


class TestLeaderboardAPI:
    """Tests for /api/leaderboard endpoint."""

    async def test_empty_leaderboard(self, client):
        """Should return empty leaderboard."""
        resp = await client.get("/api/leaderboard")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["models"] == []

    async def test_leaderboard_ordering(self, client):
        """Should return models sorted by ELO descending."""
        await client.post("/api/models", json={"name": "low", "initial_elo": 900})
        await client.post("/api/models", json={"name": "high", "initial_elo": 1200})
        resp = await client.get("/api/leaderboard")
        data = resp.json()
        assert data["total"] == 2
        assert data["models"][0]["name"] == "high"
        assert data["models"][1]["name"] == "low"

    async def test_leaderboard_pagination(self, client):
        """Should support limit and offset."""
        for i in range(5):
            await client.post("/api/models", json={"name": f"model-{i}"})
        resp = await client.get("/api/leaderboard?limit=2&offset=1")
        data = resp.json()
        assert data["total"] == 5
        assert len(data["models"]) == 2
        assert data["limit"] == 2
        assert data["offset"] == 1
