"""Tests for rate limiting middleware."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from evalarena.app import create_app


@pytest_asyncio.fixture
async def rate_limited_client():
    """Client with very low rate limit for testing."""
    app = create_app(in_memory=True, rate_limit=3, rate_window=60)
    db = app.state.db
    await db.connect()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await db.close()


@pytest.mark.asyncio
async def test_rate_limit_allows_normal_requests(rate_limited_client: AsyncClient):
    """Should allow requests within the rate limit."""
    for _ in range(3):
        r = await rate_limited_client.get("/api/stats")
        assert r.status_code == 200


@pytest.mark.asyncio
async def test_rate_limit_blocks_excess(rate_limited_client: AsyncClient):
    """Should block requests exceeding the rate limit."""
    for _ in range(3):
        await rate_limited_client.get("/api/stats")
    r = await rate_limited_client.get("/api/stats")
    assert r.status_code == 429
    assert "Rate limit" in r.json()["detail"]


@pytest.mark.asyncio
async def test_rate_limit_does_not_affect_non_api(rate_limited_client: AsyncClient):
    """Should not rate limit non-API routes."""
    for _ in range(10):
        r = await rate_limited_client.get("/health")
        assert r.status_code == 200
