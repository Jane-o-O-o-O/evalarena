"""Tests for model categories, per-category leaderboards, and API key management."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from evalarena import app as app_module
from evalarena.app import create_app


@pytest_asyncio.fixture
async def client():
    """Async test client with in-memory database."""
    app = create_app(in_memory=True)
    db = app_module._db
    await db.connect()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await db.close()


@pytest_asyncio.fixture
async def authed_client():
    """Async test client with API key authentication enabled."""
    app = create_app(in_memory=True, api_key="test-secret-key")
    db = app_module._db
    await db.connect()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await db.close()


# ── Category Tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_model_with_category(client: AsyncClient):
    """Creating a model with a category should store it."""
    r = await client.post("/api/models", json={"name": "gpt-4o", "category": "coding"})
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "gpt-4o"
    assert data["category"] == "coding"


@pytest.mark.asyncio
async def test_create_model_default_category(client: AsyncClient):
    """Models without category should default to 'general'."""
    r = await client.post("/api/models", json={"name": "llama-3"})
    assert r.status_code == 201
    assert r.json()["category"] == "general"


@pytest.mark.asyncio
async def test_list_models_filter_category(client: AsyncClient):
    """Listing models with category filter should only return matching models."""
    await client.post("/api/models", json={"name": "coder", "category": "coding"})
    await client.post("/api/models", json={"name": "writer", "category": "writing"})
    await client.post("/api/models", json={"name": "general-model"})

    r = await client.get("/api/models?category=coding")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["name"] == "coder"

    r = await client.get("/api/models")
    assert len(r.json()) == 3  # No filter = all


@pytest.mark.asyncio
async def test_leaderboard_category_filter(client: AsyncClient):
    """Leaderboard should support category filtering."""
    await client.post("/api/models", json={"name": "coder-a", "category": "coding"})
    await client.post("/api/models", json={"name": "coder-b", "category": "coding"})
    await client.post("/api/models", json={"name": "writer-a", "category": "writing"})

    r = await client.get("/api/leaderboard?category=coding")
    assert r.status_code == 200
    data = r.json()
    assert len(data["entries"]) == 2
    for entry in data["entries"]:
        assert entry["category"] == "coding"


@pytest.mark.asyncio
async def test_leaderboard_no_category_returns_all(client: AsyncClient):
    """Leaderboard without category filter returns all models."""
    await client.post("/api/models", json={"name": "a", "category": "coding"})
    await client.post("/api/models", json={"name": "b", "category": "writing"})

    r = await client.get("/api/leaderboard")
    assert r.status_code == 200
    assert len(r.json()["entries"]) == 2


@pytest.mark.asyncio
async def test_categories_endpoint(client: AsyncClient):
    """Categories endpoint should list all distinct categories."""
    await client.post("/api/models", json={"name": "a", "category": "coding"})
    await client.post("/api/models", json={"name": "b", "category": "writing"})
    await client.post("/api/models", json={"name": "c", "category": "coding"})

    r = await client.get("/api/leaderboard/categories")
    assert r.status_code == 200
    data = r.json()
    assert set(data["categories"]) == {"coding", "writing"}


@pytest.mark.asyncio
async def test_leaderboard_entry_has_category(client: AsyncClient):
    """Leaderboard entries should include category field."""
    await client.post("/api/models", json={"name": "test", "category": "reasoning"})
    r = await client.get("/api/leaderboard")
    entry = r.json()["entries"][0]
    assert entry["category"] == "reasoning"


# ── API Key Tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_api_key(client: AsyncClient):
    """Should create a new API key."""
    r = await client.post("/api/keys?name=test-key")
    assert r.status_code == 201
    data = r.json()
    assert "key" in data
    assert data["key"].startswith("evl_")
    assert data["name"] == "test-key"


@pytest.mark.asyncio
async def test_list_api_keys(client: AsyncClient):
    """Should list API keys with masked values."""
    await client.post("/api/keys?name=key-1")
    await client.post("/api/keys?name=key-2")

    r = await client.get("/api/keys")
    assert r.status_code == 200
    data = r.json()
    assert len(data["keys"]) == 2
    # Keys should be masked
    for k in data["keys"]:
        assert k["key_prefix"].endswith("...")
        assert k["active"] is True


@pytest.mark.asyncio
async def test_deactivate_api_key(client: AsyncClient):
    """Should deactivate an API key."""
    create_resp = (await client.post("/api/keys?name=to-deactivate")).json()
    key = create_resp["key"]

    r = await client.delete(f"/api/keys/{key}")
    assert r.status_code == 200

    # Verify it's deactivated
    keys = (await client.get("/api/keys")).json()["keys"]
    deactivated = [k for k in keys if not k["active"]]
    assert len(deactivated) == 1


@pytest.mark.asyncio
async def test_deactivate_nonexistent_key(client: AsyncClient):
    """Should return 404 for nonexistent key."""
    r = await client.delete("/api/keys/nonexistent")
    assert r.status_code == 404


# ── API Key Auth Middleware Tests ─────────────────────────────────────


@pytest.mark.asyncio
async def test_auth_blocks_write_without_key(authed_client: AsyncClient):
    """Write operations should be blocked without API key."""
    r = await authed_client.post("/api/models", json={"name": "test"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_auth_allows_write_with_key(authed_client: AsyncClient):
    """Write operations should succeed with correct API key."""
    r = await authed_client.post(
        "/api/models",
        json={"name": "test"},
        headers={"X-API-Key": "test-secret-key"},
    )
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_auth_allows_get_without_key(authed_client: AsyncClient):
    """GET requests should always be allowed."""
    r = await authed_client.get("/api/models")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_auth_blocks_wrong_key(authed_client: AsyncClient):
    """Wrong API key should be rejected."""
    r = await authed_client.post(
        "/api/models",
        json={"name": "test"},
        headers={"X-API-Key": "wrong-key"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_auth_allows_key_management_without_key(authed_client: AsyncClient):
    """Key management endpoints should be accessible without API key."""
    r = await authed_client.get("/api/keys")
    assert r.status_code == 200
