"""Tests for all API endpoints — models, arena, vote, leaderboard."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from evalarena.app import create_app


@pytest_asyncio.fixture
async def client():
    """Async test client with in-memory database.

    Manually connects the database since ASGITransport doesn't fire lifespan events.
    """
    app = create_app(in_memory=True)
    db = app.state.db
    await db.connect()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await db.close()


# ── Health ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    r = await client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "version" in data


# ── Models API ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_model(client: AsyncClient):
    r = await client.post("/api/models", json={"name": "gpt-4o"})
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "gpt-4o"
    assert data["rating"] == 1000.0


@pytest.mark.asyncio
async def test_create_duplicate_model(client: AsyncClient):
    await client.post("/api/models", json={"name": "gpt-4o"})
    r = await client.post("/api/models", json={"name": "gpt-4o"})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_list_models(client: AsyncClient):
    await client.post("/api/models", json={"name": "a"})
    await client.post("/api/models", json={"name": "b"})
    r = await client.get("/api/models")
    assert r.status_code == 200
    assert len(r.json()) == 2


@pytest.mark.asyncio
async def test_get_model(client: AsyncClient):
    resp = await client.post("/api/models", json={"name": "claude-3"})
    model_id = resp.json()["id"]
    r = await client.get(f"/api/models/{model_id}")
    assert r.status_code == 200
    assert r.json()["name"] == "claude-3"


@pytest.mark.asyncio
async def test_get_model_not_found(client: AsyncClient):
    r = await client.get("/api/models/nonexistent")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_model(client: AsyncClient):
    resp = await client.post("/api/models", json={"name": "to-delete"})
    model_id = resp.json()["id"]
    r = await client.delete(f"/api/models/{model_id}")
    assert r.status_code == 204
    r2 = await client.get(f"/api/models/{model_id}")
    assert r2.status_code == 404


# ── Arena API ────────────────────────────────────────────────────────


async def _create_two_models(client: AsyncClient) -> tuple[str, str]:
    """Helper to create two models and return their IDs."""
    a = (await client.post("/api/models", json={"name": "model-a"})).json()["id"]
    b = (await client.post("/api/models", json={"name": "model-b"})).json()["id"]
    return a, b


@pytest.mark.asyncio
async def test_create_battle(client: AsyncClient):
    a, b = await _create_two_models(client)
    r = await client.post("/api/arena", json={
        "prompt": "What is AI?",
        "response_a": "AI is artificial intelligence.",
        "response_b": "AI stands for artificial intelligence.",
        "model_a_id": a,
        "model_b_id": b,
    })
    assert r.status_code == 201
    data = r.json()
    assert data["prompt"] == "What is AI?"
    assert "response_a" in data
    assert "response_b" in data
    # Blind: no model identities in response
    assert "model_a_id" not in data
    assert "model_b_id" not in data


@pytest.mark.asyncio
async def test_create_battle_same_model(client: AsyncClient):
    a, _ = await _create_two_models(client)
    r = await client.post("/api/arena", json={
        "prompt": "q",
        "response_a": "a",
        "response_b": "b",
        "model_a_id": a,
        "model_b_id": a,
    })
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_create_battle_model_not_found(client: AsyncClient):
    a, _ = await _create_two_models(client)
    r = await client.post("/api/arena", json={
        "prompt": "q",
        "response_a": "a",
        "response_b": "b",
        "model_a_id": a,
        "model_b_id": "nonexistent",
    })
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_list_battles(client: AsyncClient):
    a, b = await _create_two_models(client)
    await client.post("/api/arena", json={
        "prompt": "q1", "response_a": "a1", "response_b": "b1",
        "model_a_id": a, "model_b_id": b,
    })
    r = await client.get("/api/arena")
    assert r.status_code == 200
    assert len(r.json()) == 1


@pytest.mark.asyncio
async def test_get_battle_detail(client: AsyncClient):
    a, b = await _create_two_models(client)
    resp = await client.post("/api/arena", json={
        "prompt": "q", "response_a": "a", "response_b": "b",
        "model_a_id": a, "model_b_id": b,
    })
    battle_id = resp.json()["id"]
    r = await client.get(f"/api/arena/{battle_id}")
    assert r.status_code == 200
    data = r.json()
    assert "model_a_name" in data
    assert "model_b_name" in data


# ── Vote API ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_submit_vote(client: AsyncClient):
    a, b = await _create_two_models(client)
    battle = (await client.post("/api/arena", json={
        "prompt": "q", "response_a": "a", "response_b": "b",
        "model_a_id": a, "model_b_id": b,
    })).json()

    r = await client.post("/api/vote", json={
        "battle_id": battle["id"],
        "winner": "model_a",
    })
    assert r.status_code == 201
    assert r.json()["winner"] == "model_a"


@pytest.mark.asyncio
async def test_vote_updates_elo(client: AsyncClient):
    a, b = await _create_two_models(client)
    battle = (await client.post("/api/arena", json={
        "prompt": "q", "response_a": "a", "response_b": "b",
        "model_a_id": a, "model_b_id": b,
    })).json()

    # Need to know which model is actually "model_a" in the battle (random swap)
    battle_detail = (await client.get(f"/api/arena/{battle['id']}")).json()
    # Vote for model_a (position in battle)
    await client.post("/api/vote", json={"battle_id": battle["id"], "winner": "model_a"})

    # Get the actual model that was model_a in the battle
    if battle_detail["model_a_name"] == "model-a":
        winner_name, loser_name = "model-a", "model-b"
    else:
        winner_name, loser_name = "model-b", "model-a"

    models = (await client.get("/api/models")).json()
    winner_model = next(m for m in models if m["name"] == winner_name)
    loser_model = next(m for m in models if m["name"] == loser_name)
    assert winner_model["rating"] > 1000.0
    assert loser_model["rating"] < 1000.0
    assert winner_model["wins"] == 1
    assert loser_model["losses"] == 1


@pytest.mark.asyncio
async def test_double_vote_rejected(client: AsyncClient):
    a, b = await _create_two_models(client)
    battle = (await client.post("/api/arena", json={
        "prompt": "q", "response_a": "a", "response_b": "b",
        "model_a_id": a, "model_b_id": b,
    })).json()

    await client.post("/api/vote", json={"battle_id": battle["id"], "winner": "model_a"})
    r = await client.post("/api/vote", json={"battle_id": battle["id"], "winner": "model_b"})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_vote_tie(client: AsyncClient):
    a, b = await _create_two_models(client)
    battle = (await client.post("/api/arena", json={
        "prompt": "q", "response_a": "a", "response_b": "b",
        "model_a_id": a, "model_b_id": b,
    })).json()

    r = await client.post("/api/vote", json={"battle_id": battle["id"], "winner": "tie"})
    assert r.status_code == 201
    assert r.json()["winner"] == "tie"


@pytest.mark.asyncio
async def test_vote_nonexistent_battle(client: AsyncClient):
    r = await client.post("/api/vote", json={"battle_id": "ghost", "winner": "model_a"})
    assert r.status_code == 404


# ── Leaderboard API ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_leaderboard(client: AsyncClient):
    a, b = await _create_two_models(client)
    battle = (await client.post("/api/arena", json={
        "prompt": "q", "response_a": "a", "response_b": "b",
        "model_a_id": a, "model_b_id": b,
    })).json()
    await client.post("/api/vote", json={"battle_id": battle["id"], "winner": "model_a"})

    r = await client.get("/api/leaderboard")
    assert r.status_code == 200
    data = r.json()
    assert data["total_models"] == 2
    assert len(data["entries"]) == 2
    # Winner should be ranked first
    assert data["entries"][0]["rating"] >= data["entries"][1]["rating"]


@pytest.mark.asyncio
async def test_leaderboard_empty(client: AsyncClient):
    r = await client.get("/api/leaderboard")
    assert r.status_code == 200
    assert r.json()["total_models"] == 0

# -- Model Detail API ------------------------------------------------------


@pytest.mark.asyncio
async def test_model_detail(client: AsyncClient):
    """Model detail endpoint should return match history."""
    a, b = await _create_two_models(client)
    battle = (await client.post("/api/arena", json={
        "prompt": "q", "response_a": "a", "response_b": "b",
        "model_a_id": a, "model_b_id": b,
    })).json()

    # Account for random A/B swap: check which position model-a ended up in
    battle_detail = (await client.get(f"/api/arena/{battle['id']}")).json()
    if battle_detail["model_a_name"] == "model-a":
        vote_winner = "model_a"
    else:
        vote_winner = "model_b"

    await client.post("/api/vote", json={"battle_id": battle["id"], "winner": vote_winner})

    r = await client.get(f"/api/models/{a}/detail")
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "model-a"
    assert data["total_games"] == 1
    assert data["wins"] == 1
    assert len(data["recent_battles"]) == 1
    assert data["recent_battles"][0]["result"] == "win"


@pytest.mark.asyncio
async def test_model_detail_not_found(client: AsyncClient):
    r = await client.get("/api/models/nonexistent/detail")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_model_detail_ci(client: AsyncClient):
    """Model detail should include CI."""
    a, b = await _create_two_models(client)
    r = await client.get(f"/api/models/{a}/detail")
    data = r.json()
    assert "ci_lower" in data
    assert "ci_upper" in data
    assert data["ci_lower"] < data["ci_upper"]


# -- Head-to-Head API -----------------------------------------------------


@pytest.mark.asyncio
async def test_head_to_head(client: AsyncClient):
    """Head-to-head endpoint should return comparison stats."""
    a, b = await _create_two_models(client)
    battle = (await client.post("/api/arena", json={
        "prompt": "q", "response_a": "a", "response_b": "b",
        "model_a_id": a, "model_b_id": b,
    })).json()
    await client.post("/api/vote", json={"battle_id": battle["id"], "winner": "model_a"})

    r = await client.get(f"/api/models/{a}/head-to-head/{b}")
    assert r.status_code == 200
    data = r.json()
    assert data["model_a"] == "model-a"
    assert data["model_b"] == "model-b"
    assert data["total_battles"] == 1


@pytest.mark.asyncio
async def test_head_to_head_nonexistent(client: AsyncClient):
    a, _ = await _create_two_models(client)
    r = await client.get(f"/api/models/{a}/head-to-head/ghost")
    assert r.status_code == 404


# -- Stats API -------------------------------------------------------------


@pytest.mark.asyncio
async def test_stats_endpoint(client: AsyncClient):
    """Stats endpoint should return aggregate data."""
    a, b = await _create_two_models(client)
    battle = (await client.post("/api/arena", json={
        "prompt": "q", "response_a": "a", "response_b": "b",
        "model_a_id": a, "model_b_id": b,
    })).json()
    await client.post("/api/vote", json={"battle_id": battle["id"], "winner": "model_a"})

    r = await client.get("/api/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["total_models"] == 2
    assert data["total_battles"] == 1
    assert data["total_votes"] == 1
    assert data["avg_rating"] > 0


@pytest.mark.asyncio
async def test_stats_empty(client: AsyncClient):
    r = await client.get("/api/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["total_models"] == 0


# -- CI in Leaderboard ----------------------------------------------------


@pytest.mark.asyncio
async def test_leaderboard_has_ci(client: AsyncClient):
    """Leaderboard entries should include CI."""
    a, b = await _create_two_models(client)
    r = await client.get("/api/leaderboard")
    data = r.json()
    for entry in data["entries"]:
        assert "ci_lower" in entry
        assert "ci_upper" in entry


# -- Unvoted Battles Filter ------------------------------------------------


@pytest.mark.asyncio
async def test_list_battles_unvoted_only(client: AsyncClient):
    """Should filter to only unvoted battles."""
    a, b = await _create_two_models(client)
    # Create 3 battles
    for i in range(3):
        await client.post("/api/arena", json={
            "prompt": f"q{i}", "response_a": "a", "response_b": "b",
            "model_a_id": a, "model_b_id": b,
        })
    # Vote on 1
    battles = (await client.get("/api/arena")).json()
    await client.post("/api/vote", json={"battle_id": battles[0]["id"], "winner": "model_a"})

    r = await client.get("/api/arena?unvoted_only=true")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    for b in data:
        assert b["voted"] is False


@pytest.mark.asyncio
async def test_battle_out_has_voted(client: AsyncClient):
    """BattleOut should include voted field."""
    a, b = await _create_two_models(client)
    await client.post("/api/arena", json={
        "prompt": "q", "response_a": "a", "response_b": "b",
        "model_a_id": a, "model_b_id": b,
    })
    r = await client.get("/api/arena")
    assert r.json()[0]["voted"] is False


# -- Model CI in API -------------------------------------------------------


@pytest.mark.asyncio
async def test_model_out_has_ci(client: AsyncClient):
    """ModelOut should include CI fields."""
    resp = await client.post("/api/models", json={"name": "ci-model"})
    data = resp.json()
    assert "ci_lower" in data
    assert "ci_upper" in data
