"""Tests for new features: model metadata, search, rating history, battles page, CLI commands."""

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


# ── Model Metadata Tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_model_with_metadata(client: AsyncClient):
    """Creating a model with description, organization, parameter_count should work."""
    r = await client.post("/api/models", json={
        "name": "gpt-4o",
        "category": "general",
        "description": "OpenAI's most capable model",
        "organization": "OpenAI",
        "parameter_count": "200B",
    })
    assert r.status_code == 201
    data = r.json()
    assert data["description"] == "OpenAI's most capable model"
    assert data["organization"] == "OpenAI"
    assert data["parameter_count"] == "200B"


@pytest.mark.asyncio
async def test_model_out_includes_metadata(client: AsyncClient):
    """ModelOut response should include metadata fields."""
    await client.post("/api/models", json={
        "name": "claude-3",
        "organization": "Anthropic",
        "parameter_count": "175B",
    })
    r = await client.get("/api/models")
    models = r.json()
    assert len(models) == 1
    assert models[0]["organization"] == "Anthropic"
    assert models[0]["parameter_count"] == "175B"


@pytest.mark.asyncio
async def test_model_detail_includes_metadata(client: AsyncClient):
    """ModelDetail endpoint should include metadata fields."""
    resp = await client.post("/api/models", json={
        "name": "llama-3",
        "category": "open-source",
        "description": "Meta's open LLM",
        "organization": "Meta",
        "parameter_count": "70B",
    })
    model_id = resp.json()["id"]

    r = await client.get(f"/api/models/{model_id}/detail")
    assert r.status_code == 200
    data = r.json()
    assert data["description"] == "Meta's open LLM"
    assert data["organization"] == "Meta"
    assert data["parameter_count"] == "70B"


@pytest.mark.asyncio
async def test_model_metadata_defaults_empty(client: AsyncClient):
    """Metadata fields should default to empty strings."""
    r = await client.post("/api/models", json={"name": "basic-model"})
    assert r.status_code == 201
    data = r.json()
    assert data["description"] == ""
    assert data["organization"] == ""
    assert data["parameter_count"] == ""


# ── Model Search Tests ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_models_by_name(client: AsyncClient):
    """Search endpoint should find models by name."""
    await client.post("/api/models", json={"name": "gpt-4o"})
    await client.post("/api/models", json={"name": "gpt-3.5-turbo"})
    await client.post("/api/models", json={"name": "claude-3"})

    r = await client.get("/api/models/search?q=gpt")
    assert r.status_code == 200
    results = r.json()
    assert len(results) == 2
    names = {m["name"] for m in results}
    assert "gpt-4o" in names
    assert "gpt-3.5-turbo" in names


@pytest.mark.asyncio
async def test_search_models_by_organization(client: AsyncClient):
    """Search endpoint should find models by organization."""
    await client.post("/api/models", json={
        "name": "gpt-4o", "organization": "OpenAI"
    })
    await client.post("/api/models", json={
        "name": "claude-3", "organization": "Anthropic"
    })
    await client.post("/api/models", json={
        "name": "gpt-3.5", "organization": "OpenAI"
    })

    r = await client.get("/api/models/search?q=Anthropic")
    assert r.status_code == 200
    results = r.json()
    assert len(results) == 1
    assert results[0]["name"] == "claude-3"


@pytest.mark.asyncio
async def test_search_models_empty_query():
    """Search with empty query should return 422."""
    app = create_app(in_memory=True)
    db = app.state.db
    await db.connect()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/api/models/search?q=")
        assert r.status_code == 422
    await db.close()


@pytest.mark.asyncio
async def test_search_models_no_results(client: AsyncClient):
    """Search with no matching results should return empty list."""
    await client.post("/api/models", json={"name": "gpt-4o"})
    r = await client.get("/api/models/search?q=nonexistent")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_list_models_with_search_param(client: AsyncClient):
    """List models endpoint should accept search query param."""
    await client.post("/api/models", json={"name": "gpt-4o"})
    await client.post("/api/models", json={"name": "claude-3"})

    r = await client.get("/api/models?search=gpt")
    assert r.status_code == 200
    results = r.json()
    assert len(results) == 1
    assert results[0]["name"] == "gpt-4o"


# ── Rating History Tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rating_history_empty(client: AsyncClient):
    """Rating history for a model with no battles should be empty."""
    resp = await client.post("/api/models", json={"name": "model-a"})
    model_id = resp.json()["id"]

    r = await client.get(f"/api/models/{model_id}/rating-history")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_rating_history_after_vote(client: AsyncClient):
    """Rating history should show rating after each voted battle."""
    a = (await client.post("/api/models", json={"name": "model-a"})).json()["id"]
    b = (await client.post("/api/models", json={"name": "model-b"})).json()["id"]

    # Create and vote on a battle
    battle = (await client.post("/api/arena", json={
        "prompt": "test question", "response_a": "a", "response_b": "b",
        "model_a_id": a, "model_b_id": b,
    })).json()

    # Determine position for correct vote
    detail = (await client.get(f"/api/arena/{battle['id']}")).json()
    if detail["model_a_name"] == "model-a":
        vote_winner = "model_a"
    else:
        vote_winner = "model_b"

    await client.post("/api/vote", json={"battle_id": battle["id"], "winner": vote_winner})

    # Check rating history
    r = await client.get(f"/api/models/{a}/rating-history")
    assert r.status_code == 200
    history = r.json()
    assert len(history) == 1
    assert history[0]["result"] == "win"
    assert history[0]["rating_change"] > 0
    assert history[0]["opponent_name"] == "model-b"
    assert history[0]["rating"] > 1000.0


@pytest.mark.asyncio
async def test_rating_history_chronological(client: AsyncClient):
    """Rating history should be in chronological order."""
    a = (await client.post("/api/models", json={"name": "model-a"})).json()["id"]
    b = (await client.post("/api/models", json={"name": "model-b"})).json()["id"]

    # Create 3 battles
    for i in range(3):
        battle = (await client.post("/api/arena", json={
            "prompt": f"question {i}", "response_a": "a", "response_b": "b",
            "model_a_id": a, "model_b_id": b,
        })).json()

        detail = (await client.get(f"/api/arena/{battle['id']}")).json()
        if detail["model_a_name"] == "model-a":
            vote_winner = "model_a"
        else:
            vote_winner = "model_b"

        await client.post("/api/vote", json={"battle_id": battle["id"], "winner": vote_winner})

    r = await client.get(f"/api/models/{a}/rating-history")
    history = r.json()
    assert len(history) == 3
    # Ratings should generally increase (winner keeps winning)
    assert history[-1]["rating"] > history[0]["rating"]


@pytest.mark.asyncio
async def test_rating_history_not_found():
    """Rating history for nonexistent model should return 404."""
    app = create_app(in_memory=True)
    db = app.state.db
    await db.connect()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/api/models/nonexistent/rating-history")
        assert r.status_code == 404
    await db.close()


# ── Battles Page Tests ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_battles_page_empty(client: AsyncClient):
    """Battles page should work with no battles."""
    r = await client.get("/battles")
    assert r.status_code == 200
    assert "对战历史" in r.text


@pytest.mark.asyncio
async def test_battles_page_shows_battles(client: AsyncClient):
    """Battles page should display past battles with model names."""
    a = (await client.post("/api/models", json={"name": "gpt-4o"})).json()["id"]
    b = (await client.post("/api/models", json={"name": "claude-3"})).json()["id"]

    battle = (await client.post("/api/arena", json={
        "prompt": "What is AI?", "response_a": "r1", "response_b": "r2",
        "model_a_id": a, "model_b_id": b,
    })).json()

    detail = (await client.get(f"/api/arena/{battle['id']}")).json()
    if detail["model_a_name"] == "gpt-4o":
        vote_winner = "model_a"
    else:
        vote_winner = "model_b"

    await client.post("/api/vote", json={"battle_id": battle["id"], "winner": vote_winner})

    r = await client.get("/battles")
    assert r.status_code == 200
    assert "gpt-4o" in r.text
    assert "claude-3" in r.text
    assert "What is AI?" in r.text


@pytest.mark.asyncio
async def test_battles_page_pagination(client: AsyncClient):
    """Battles page should support pagination."""
    a = (await client.post("/api/models", json={"name": "m-a"})).json()["id"]
    b = (await client.post("/api/models", json={"name": "m-b"})).json()["id"]

    # Create 3 battles
    for i in range(3):
        battle = (await client.post("/api/arena", json={
            "prompt": f"q{i}", "response_a": "a", "response_b": "b",
            "model_a_id": a, "model_b_id": b,
        })).json()
        detail = (await client.get(f"/api/arena/{battle['id']}")).json()
        if detail["model_a_name"] == "m-a":
            vote_winner = "model_a"
        else:
            vote_winner = "model_b"
        await client.post("/api/vote", json={"battle_id": battle["id"], "winner": vote_winner})

    r = await client.get("/battles?limit=2&offset=0")
    assert r.status_code == 200
    assert "下一页" in r.text


@pytest.mark.asyncio
async def test_battles_nav_link(client: AsyncClient):
    """Base template should have battles nav link."""
    r = await client.get("/")
    assert "/battles" in r.text


# ── Database Method Tests ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_models_db(client: AsyncClient):
    """Database search_models method should work."""
    db = client._transport.app.state.db  # type: ignore

    from evalarena.db.models import ModelCreate
    await db.create_model(ModelCreate(name="gpt-4o", organization="OpenAI"))
    await db.create_model(ModelCreate(name="gpt-3.5", organization="OpenAI"))
    await db.create_model(ModelCreate(name="claude-3", organization="Anthropic"))

    results = await db.search_models("gpt")
    assert len(results) == 2

    results = await db.search_models("Anthropic")
    assert len(results) == 1
    assert results[0].name == "claude-3"


@pytest.mark.asyncio
async def test_get_rating_history_db(client: AsyncClient):
    """Database get_rating_history method should work."""
    db = client._transport.app.state.db  # type: ignore

    from evalarena.db.models import ModelCreate
    a = await db.create_model(ModelCreate(name="model-a"))
    b = await db.create_model(ModelCreate(name="model-b"))

    # No battles yet
    history = await db.get_rating_history(a.id)
    assert history == []


@pytest.mark.asyncio
async def test_get_battles_with_details_db(client: AsyncClient):
    """Database get_battles_with_details method should return battle details."""
    db = client._transport.app.state.db  # type: ignore

    from evalarena.db.models import ModelCreate, BattleCreate
    a = await db.create_model(ModelCreate(name="alpha"))
    b = await db.create_model(ModelCreate(name="beta"))

    await db.create_battle(BattleCreate(
        prompt="test", response_a="r1", response_b="r2",
        model_a_id=a.id, model_b_id=b.id,
    ))

    battles = await db.get_battles_with_details()
    assert len(battles) == 1
    assert battles[0]["model_a_name"] == "alpha"
    assert battles[0]["model_b_name"] == "beta"
    assert battles[0]["winner"] is None


# ── CLI Command Tests ────────────────────────────────────────────────


def test_cli_add_model_with_metadata(tmp_path):
    """CLI add-model should support metadata options."""
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(main, ["init-db", "--db", db_path])

    result = runner.invoke(main, [
        "add-model", "gpt-4o",
        "--category", "general",
        "--description", "OpenAI's flagship model",
        "--organization", "OpenAI",
        "--params", "200B",
        "--db", db_path,
    ])
    assert result.exit_code == 0
    assert "OpenAI" in result.output
    assert "200B" in result.output


def test_cli_search_models(tmp_path):
    """CLI search-models command should work."""
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(main, ["init-db", "--db", db_path])
    runner.invoke(main, ["add-model", "gpt-4o", "--db", db_path])
    runner.invoke(main, ["add-model", "gpt-3.5-turbo", "--db", db_path])
    runner.invoke(main, ["add-model", "claude-3", "--db", db_path])

    result = runner.invoke(main, ["search-models", "gpt", "--db", db_path])
    assert result.exit_code == 0
    assert "gpt-4o" in result.output
    assert "gpt-3.5-turbo" in result.output
    assert "claude-3" not in result.output


def test_cli_search_models_no_results(tmp_path):
    """CLI search-models with no matches should show message."""
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(main, ["init-db", "--db", db_path])
    runner.invoke(main, ["add-model", "gpt-4o", "--db", db_path])

    result = runner.invoke(main, ["search-models", "nonexistent", "--db", db_path])
    assert result.exit_code == 0
    assert "No models matching" in result.output


def test_cli_delete_model(tmp_path):
    """CLI delete-model command should work."""
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(main, ["init-db", "--db", db_path])
    runner.invoke(main, ["add-model", "gpt-4o", "--db", db_path])

    result = runner.invoke(main, ["delete-model", "gpt-4o", "--yes", "--db", db_path])
    assert result.exit_code == 0
    assert "Deleted" in result.output

    # Verify model is gone
    result = runner.invoke(main, ["list-models", "--db", db_path])
    assert "gpt-4o" not in result.output


def test_cli_delete_model_not_found(tmp_path):
    """CLI delete-model should handle missing model."""
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(main, ["init-db", "--db", db_path])

    result = runner.invoke(main, ["delete-model", "ghost", "--yes", "--db", db_path])
    assert result.exit_code == 0
    assert "not found" in result.output


def test_cli_reset_db(tmp_path):
    """CLI reset-db command should delete and reinitialize the database."""
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(main, ["init-db", "--db", db_path])
    runner.invoke(main, ["add-model", "gpt-4o", "--db", db_path])

    result = runner.invoke(main, ["reset-db", "--yes", "--db", db_path])
    assert result.exit_code == 0
    assert "reset" in result.output.lower()

    # Database should be empty now
    result = runner.invoke(main, ["list-models", "--db", db_path])
    assert "No models" in result.output


def test_cli_search_help():
    """CLI search-models --help should work."""
    runner = CliRunner()
    result = runner.invoke(main, ["search-models", "--help"])
    assert result.exit_code == 0
    assert "query" in result.output.lower() or "QUERY" in result.output


def test_cli_delete_model_help():
    """CLI delete-model --help should work."""
    runner = CliRunner()
    result = runner.invoke(main, ["delete-model", "--help"])
    assert result.exit_code == 0
    assert "name" in result.output.lower() or "NAME" in result.output


def test_cli_reset_db_help():
    """CLI reset-db --help should work."""
    runner = CliRunner()
    result = runner.invoke(main, ["reset-db", "--help"])
    assert result.exit_code == 0


# ── Leaderboard Entry Search Tests ──────────────────────────────────


@pytest.mark.asyncio
async def test_leaderboard_still_works_with_metadata(client: AsyncClient):
    """Leaderboard should still work after adding metadata fields."""
    await client.post("/api/models", json={
        "name": "gpt-4o", "organization": "OpenAI", "parameter_count": "200B"
    })
    await client.post("/api/models", json={
        "name": "claude-3", "organization": "Anthropic"
    })

    r = await client.get("/api/leaderboard")
    assert r.status_code == 200
    data = r.json()
    assert data["total_models"] == 2
    assert len(data["entries"]) == 2


@pytest.mark.asyncio
async def test_model_detail_page_shows_metadata(client: AsyncClient):
    """Model detail web page should show metadata."""
    resp = await client.post("/api/models", json={
        "name": "gpt-4o",
        "description": "Flagship model",
        "organization": "OpenAI",
        "parameter_count": "200B",
    })
    model_id = resp.json()["id"]

    r = await client.get(f"/model/{model_id}")
    assert r.status_code == 200
    assert "OpenAI" in r.text
    assert "200B" in r.text
    assert "Flagship model" in r.text
