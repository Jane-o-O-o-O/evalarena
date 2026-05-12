"""Tests for new features: rating_change, CLI commands, landing page."""

import pytest
import pytest_asyncio
from click.testing import CliRunner
from httpx import ASGITransport, AsyncClient

from evalarena.app import create_app
from evalarena.cli import main


@pytest_asyncio.fixture
async def client():
    """Async test client with in-memory database."""
    app = create_app(in_memory=True)
    db = app.state.db
    await db.connect()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await db.close()


# ── Rating Change Tests ──────────────────────────────────────────────


async def _create_two_models(client: AsyncClient) -> tuple[str, str]:
    """Helper to create two models and return their IDs."""
    a = (await client.post("/api/models", json={"name": "model-a"})).json()["id"]
    b = (await client.post("/api/models", json={"name": "model-b"})).json()["id"]
    return a, b


@pytest.mark.asyncio
async def test_rating_change_after_vote(client: AsyncClient):
    """BattleSummary should show actual rating change after voting."""
    a, b = await _create_two_models(client)
    battle = (await client.post("/api/arena", json={
        "prompt": "q", "response_a": "a", "response_b": "b",
        "model_a_id": a, "model_b_id": b,
    })).json()

    # Check which model ended up in position A (random swap)
    battle_detail = (await client.get(f"/api/arena/{battle['id']}")).json()
    if battle_detail["model_a_name"] == "model-a":
        vote_winner = "model_a"
        winner_id = a
    else:
        vote_winner = "model_b"
        winner_id = a  # model-a is in position B, vote for B

    await client.post("/api/vote", json={"battle_id": battle["id"], "winner": vote_winner})

    # Check rating change in model detail for the winner
    r = await client.get(f"/api/models/{winner_id}/detail")
    assert r.status_code == 200
    data = r.json()
    assert len(data["recent_battles"]) == 1
    rating_change = data["recent_battles"][0]["rating_change"]
    # Winner should have positive rating change
    assert rating_change > 0


@pytest.mark.asyncio
async def test_rating_change_loss(client: AsyncClient):
    """Loser should have negative rating change."""
    a, b = await _create_two_models(client)
    battle = (await client.post("/api/arena", json={
        "prompt": "q", "response_a": "a", "response_b": "b",
        "model_a_id": a, "model_b_id": b,
    })).json()

    # Vote for model_a (position) - so model_b loses
    await client.post("/api/vote", json={"battle_id": battle["id"], "winner": "model_a"})

    # Get model_b detail (the loser)
    battle_detail = (await client.get(f"/api/arena/{battle['id']}")).json()
    if battle_detail["model_a_name"] == "model-a":
        loser_id = b
    else:
        loser_id = a

    r = await client.get(f"/api/models/{loser_id}/detail")
    data = r.json()
    rating_change = data["recent_battles"][0]["rating_change"]
    assert rating_change < 0


@pytest.mark.asyncio
async def test_rating_change_tie(client: AsyncClient):
    """Tie should have small rating change (based on expected scores)."""
    a, b = await _create_two_models(client)
    battle = (await client.post("/api/arena", json={
        "prompt": "q", "response_a": "a", "response_b": "b",
        "model_a_id": a, "model_b_id": b,
    })).json()

    await client.post("/api/vote", json={"battle_id": battle["id"], "winner": "tie"})

    r = await client.get(f"/api/models/{a}/detail")
    data = r.json()
    rating_change = data["recent_battles"][0]["rating_change"]
    # For equal ratings, tie should give 0 change
    assert abs(rating_change) < 0.1


@pytest.mark.asyncio
async def test_rating_change_pending_battle(client: AsyncClient):
    """Pending (unvoted) battle should have 0 rating change."""
    a, b = await _create_two_models(client)
    await client.post("/api/arena", json={
        "prompt": "q", "response_a": "a", "response_b": "b",
        "model_a_id": a, "model_b_id": b,
    })

    r = await client.get(f"/api/models/{a}/detail")
    data = r.json()
    assert len(data["recent_battles"]) == 1
    assert data["recent_battles"][0]["rating_change"] == 0.0
    assert data["recent_battles"][0]["result"] == "pending"


# ── Landing Page Tests ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_landing_page(client: AsyncClient):
    """Landing page should return HTML with stats."""
    r = await client.get("/")
    assert r.status_code == 200
    assert "EvalArena" in r.text
    assert "Models" in r.text
    assert "Battles" in r.text


@pytest.mark.asyncio
async def test_landing_page_shows_top_models(client: AsyncClient):
    """Landing page should show top 5 models."""
    await client.post("/api/models", json={"name": "gpt-4o"})
    await client.post("/api/models", json={"name": "claude-3"})

    r = await client.get("/")
    assert r.status_code == 200
    assert "gpt-4o" in r.text
    assert "claude-3" in r.text


# ── CLI Tests ────────────────────────────────────────────────────────


def test_cli_stats_empty(tmp_path):
    """CLI stats command should work with empty database."""
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    result = runner.invoke(main, ["init-db", "--db", db_path])
    assert result.exit_code == 0

    result = runner.invoke(main, ["stats", "--db", db_path])
    assert result.exit_code == 0
    assert "Models" in result.output
    assert "Battles" in result.output


def test_cli_stats_with_data(tmp_path):
    """CLI stats command should show correct counts."""
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()

    # Init and add models
    runner.invoke(main, ["init-db", "--db", db_path])
    runner.invoke(main, ["add-model", "gpt-4o", "--db", db_path])
    runner.invoke(main, ["add-model", "claude-3", "--db", db_path])

    result = runner.invoke(main, ["stats", "--db", db_path])
    assert result.exit_code == 0
    assert "2" in result.output  # 2 models


def test_cli_head_to_head(tmp_path):
    """CLI head-to-head command should work."""
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()

    runner.invoke(main, ["init-db", "--db", db_path])
    runner.invoke(main, ["add-model", "gpt-4o", "--db", db_path])
    runner.invoke(main, ["add-model", "claude-3", "--db", db_path])

    result = runner.invoke(main, ["head-to-head", "gpt-4o", "claude-3", "--db", db_path])
    assert result.exit_code == 0
    assert "gpt-4o" in result.output
    assert "claude-3" in result.output


def test_cli_head_to_head_not_found(tmp_path):
    """CLI head-to-head should handle missing models."""
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()

    runner.invoke(main, ["init-db", "--db", db_path])
    runner.invoke(main, ["add-model", "gpt-4o", "--db", db_path])

    result = runner.invoke(main, ["head-to-head", "gpt-4o", "ghost", "--db", db_path])
    assert result.exit_code == 0
    assert "not found" in result.output


def test_cli_stats_help():
    """CLI stats --help should work."""
    runner = CliRunner()
    result = runner.invoke(main, ["stats", "--help"])
    assert result.exit_code == 0
    assert "statistics" in result.output.lower() or "stats" in result.output.lower()
