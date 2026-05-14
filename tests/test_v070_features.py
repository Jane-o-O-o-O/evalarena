"""Tests for v0.7.0 features: tournaments, battle search, win streaks,
webhooks, backup/restore, and webhook integration in vote flow."""

from __future__ import annotations

import json
import pytest
from httpx import ASGITransport, AsyncClient

from evalarena.app import create_app
from evalarena.db.database import Database
from evalarena.db.models import (
    BattleCreate,
    ModelCreate,
    VoteCreate,
    Winner,
    TournamentCreate,
    WebhookCreate,
)


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
async def app():
    """Create a test app with in-memory database."""
    application = create_app(in_memory=True)
    yield application


@pytest.fixture
async def client(app):
    """Create a test HTTP client."""
    db: Database = app.state.db
    await db.connect()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await db.close()


@pytest.fixture
async def db(app):
    """Get the database instance."""
    database: Database = app.state.db
    await database.connect()
    yield database
    await database.close()


async def _register_model(
    client: AsyncClient, name: str = "test-model", category: str = "general", **kwargs
) -> str:
    """Helper: register a model and return its ID."""
    payload = {"name": name, "category": category, **kwargs}
    resp = await client.post("/api/models", json=payload)
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_battle(
    client: AsyncClient,
    model_a_id: str,
    model_b_id: str,
    prompt: str = "test prompt",
) -> str:
    """Helper: create a battle and return its ID."""
    resp = await client.post(
        "/api/arena",
        json={
            "prompt": prompt,
            "response_a": "Response A content",
            "response_b": "Response B content",
            "model_a_id": model_a_id,
            "model_b_id": model_b_id,
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _vote_battle(
    client: AsyncClient, battle_id: str, winner: str = "model_a"
) -> None:
    """Helper: vote on a battle."""
    resp = await client.post(
        "/api/vote", json={"battle_id": battle_id, "winner": winner}
    )
    assert resp.status_code == 201


async def _setup_models_and_battles(client: AsyncClient, n_models: int = 3):
    """Helper: create N models and some battles between them."""
    model_ids = []
    for i in range(n_models):
        mid = await _register_model(client, f"model-{chr(97+i)}")
        model_ids.append(mid)

    battle_ids = []
    for i in range(n_models):
        for j in range(i + 1, n_models):
            bid = await _create_battle(
                client,
                model_ids[i],
                model_ids[j],
                prompt=f"Question for {chr(97+i)} vs {chr(97+j)}",
            )
            battle_ids.append(bid)

    return model_ids, battle_ids


# ── Tournament DB Tests ────────────────────────────────────────────


class TestTournamentDB:
    """Tests for tournament database operations."""

    async def test_create_tournament(self, db: Database):
        """Test creating a round-robin tournament."""
        m1 = await db.create_model(ModelCreate(name="t-a"))
        m2 = await db.create_model(ModelCreate(name="t-b"))
        m3 = await db.create_model(ModelCreate(name="t-c"))

        result = await db.create_tournament(
            name="Test Tournament",
            model_ids=[m1.id, m2.id, m3.id],
            category="coding",
        )
        assert result["name"] == "Test Tournament"
        assert result["status"] == "pending"
        assert result["total_matches"] == 3  # C(3,2) = 3
        assert result["completed_matches"] == 0
        assert len(result["model_ids"]) == 3

    async def test_create_tournament_two_models(self, db: Database):
        """Tournament with 2 models has 1 match."""
        m1 = await db.create_model(ModelCreate(name="duo-a"))
        m2 = await db.create_model(ModelCreate(name="duo-b"))

        result = await db.create_tournament(
            name="Duo Cup", model_ids=[m1.id, m2.id]
        )
        assert result["total_matches"] == 1

    async def test_get_tournament(self, db: Database):
        """Get tournament with standings."""
        m1 = await db.create_model(ModelCreate(name="get-a"))
        m2 = await db.create_model(ModelCreate(name="get-b"))

        created = await db.create_tournament(
            name="Get Cup", model_ids=[m1.id, m2.id]
        )
        tournament = await db.get_tournament(created["id"])
        assert tournament is not None
        assert tournament["name"] == "Get Cup"
        assert len(tournament["matches"]) == 1
        assert len(tournament["standings"]) == 2

    async def test_list_tournaments(self, db: Database):
        """List tournaments with status filter."""
        m1 = await db.create_model(ModelCreate(name="lst-a"))
        m2 = await db.create_model(ModelCreate(name="lst-b"))

        await db.create_tournament(name="T1", model_ids=[m1.id, m2.id])
        await db.create_tournament(name="T2", model_ids=[m1.id, m2.id])

        all_t = await db.list_tournaments()
        assert len(all_t) == 2

        pending = await db.list_tournaments(status="pending")
        assert len(pending) == 2

        completed = await db.list_tournaments(status="completed")
        assert len(completed) == 0

    async def test_tournament_lifecycle(self, db: Database):
        """Test tournament status transitions."""
        m1 = await db.create_model(ModelCreate(name="life-a"))
        m2 = await db.create_model(ModelCreate(name="life-b"))

        created = await db.create_tournament(
            name="Lifecycle Cup", model_ids=[m1.id, m2.id]
        )
        tid = created["id"]

        # Start
        assert await db.start_tournament(tid) is True
        t = await db.get_tournament(tid)
        assert t["status"] == "in_progress"

        # Can't start again
        assert await db.start_tournament(tid) is False

        # Complete
        assert await db.complete_tournament(tid) is True
        t = await db.get_tournament(tid)
        assert t["status"] == "completed"

    async def test_cancel_tournament(self, db: Database):
        """Test cancelling a tournament."""
        m1 = await db.create_model(ModelCreate(name="cancel-a"))
        m2 = await db.create_model(ModelCreate(name="cancel-b"))

        created = await db.create_tournament(
            name="Cancel Cup", model_ids=[m1.id, m2.id]
        )
        tid = created["id"]

        assert await db.cancel_tournament(tid) is True
        t = await db.get_tournament(tid)
        assert t["status"] == "cancelled"

    async def test_record_match_battle(self, db: Database):
        """Record a battle result for a tournament match."""
        m1 = await db.create_model(ModelCreate(name="rec-a"))
        m2 = await db.create_model(ModelCreate(name="rec-b"))

        created = await db.create_tournament(
            name="Record Cup", model_ids=[m1.id, m2.id]
        )
        tid = created["id"]

        tournament = await db.get_tournament(tid)
        match_id = tournament["matches"][0]["id"]

        # Create a battle
        battle = await db.create_battle(BattleCreate(
            prompt="test", response_a="a", response_b="b",
            model_a_id=m1.id, model_b_id=m2.id,
        ))

        # Record it
        assert await db.record_match_battle(match_id, battle.id, m1.id) is True

        # Verify match completed
        tournament = await db.get_tournament(tid)
        assert tournament["matches"][0]["status"] == "completed"
        assert tournament["matches"][0]["winner_model_id"] == m1.id
        assert battle.id in tournament["matches"][0]["battle_ids"]

    async def test_tournament_standings(self, db: Database):
        """Standings update correctly as matches complete."""
        m1 = await db.create_model(ModelCreate(name="stand-a"))
        m2 = await db.create_model(ModelCreate(name="stand-b"))
        m3 = await db.create_model(ModelCreate(name="stand-c"))

        created = await db.create_tournament(
            name="Standings Cup", model_ids=[m1.id, m2.id, m3.id]
        )
        tid = created["id"]

        tournament = await db.get_tournament(tid)

        # Complete first match: m1 beats m2
        match_1 = next(
            m for m in tournament["matches"]
            if {m["model_a_id"], m["model_b_id"]} == {m1.id, m2.id}
        )
        battle1 = await db.create_battle(BattleCreate(
            prompt="q1", response_a="a", response_b="b",
            model_a_id=m1.id, model_b_id=m2.id,
        ))
        await db.record_match_battle(match_1["id"], battle1.id, m1.id)

        # Check standings
        tournament = await db.get_tournament(tid)
        standings = {s["model_id"]: s for s in tournament["standings"]}
        assert standings[m1.id]["wins"] == 1
        assert standings[m1.id]["points"] == 1.0
        assert standings[m2.id]["losses"] == 1

    async def test_get_nonexistent_tournament(self, db: Database):
        """Get nonexistent tournament returns None."""
        assert await db.get_tournament("nonexistent") is None


# ── Tournament API Tests ───────────────────────────────────────────


class TestTournamentAPI:
    """Tests for tournament API endpoints."""

    async def test_create_tournament_api(self, client: AsyncClient):
        """POST /api/tournaments creates a tournament."""
        a_id = await _register_model(client, "api-t-a")
        b_id = await _register_model(client, "api-t-b")

        resp = await client.post("/api/tournaments", json={
            "name": "API Tournament",
            "model_ids": [a_id, b_id],
            "category": "coding",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "API Tournament"
        assert data["total_matches"] == 1

    async def test_create_tournament_invalid_models(self, client: AsyncClient):
        """Creating tournament with invalid model IDs fails."""
        resp = await client.post("/api/tournaments", json={
            "name": "Bad Tournament",
            "model_ids": ["nonexistent-a", "nonexistent-b"],
        })
        assert resp.status_code == 404

    async def test_create_tournament_duplicate_models(self, client: AsyncClient):
        """Creating tournament with duplicate model IDs fails."""
        a_id = await _register_model(client, "dup-a")
        resp = await client.post("/api/tournaments", json={
            "name": "Dup Tournament",
            "model_ids": [a_id, a_id],
        })
        assert resp.status_code == 400

    async def test_list_tournaments_api(self, client: AsyncClient):
        """GET /api/tournaments lists tournaments."""
        a_id = await _register_model(client, "lst-api-a")
        b_id = await _register_model(client, "lst-api-b")
        await client.post("/api/tournaments", json={
            "name": "T1", "model_ids": [a_id, b_id],
        })

        resp = await client.get("/api/tournaments")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1

    async def test_get_tournament_api(self, client: AsyncClient):
        """GET /api/tournaments/{id} returns tournament details."""
        a_id = await _register_model(client, "get-api-a")
        b_id = await _register_model(client, "get-api-b")
        create_resp = await client.post("/api/tournaments", json={
            "name": "Get Tournament", "model_ids": [a_id, b_id],
        })
        tid = create_resp.json()["id"]

        resp = await client.get(f"/api/tournaments/{tid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Get Tournament"
        assert "standings" in data
        assert "matches" in data

    async def test_start_tournament_api(self, client: AsyncClient):
        """POST /api/tournaments/{id}/start changes status."""
        a_id = await _register_model(client, "start-a")
        b_id = await _register_model(client, "start-b")
        create_resp = await client.post("/api/tournaments", json={
            "name": "Start Tournament", "model_ids": [a_id, b_id],
        })
        tid = create_resp.json()["id"]

        resp = await client.post(f"/api/tournaments/{tid}/start")
        assert resp.status_code == 200
        assert resp.json()["status"] == "in_progress"

    async def test_complete_tournament_api(self, client: AsyncClient):
        """POST /api/tournaments/{id}/complete changes status."""
        a_id = await _register_model(client, "complete-a")
        b_id = await _register_model(client, "complete-b")
        create_resp = await client.post("/api/tournaments", json={
            "name": "Complete Tournament", "model_ids": [a_id, b_id],
        })
        tid = create_resp.json()["id"]

        # Must start first
        await client.post(f"/api/tournaments/{tid}/start")
        resp = await client.post(f"/api/tournaments/{tid}/complete")
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

    async def test_cancel_tournament_api(self, client: AsyncClient):
        """POST /api/tournaments/{id}/cancel cancels tournament."""
        a_id = await _register_model(client, "cancel-api-a")
        b_id = await _register_model(client, "cancel-api-b")
        create_resp = await client.post("/api/tournaments", json={
            "name": "Cancel Tournament", "model_ids": [a_id, b_id],
        })
        tid = create_resp.json()["id"]

        resp = await client.post(f"/api/tournaments/{tid}/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    async def test_tournament_not_found(self, client: AsyncClient):
        """Getting nonexistent tournament returns 404."""
        resp = await client.get("/api/tournaments/nonexistent")
        assert resp.status_code == 404


# ── Tournament CLI Tests ───────────────────────────────────────────


class TestTournamentCLI:
    """Tests for tournament CLI commands."""

    def test_cli_create_tournament(self, tmp_path):
        """Test CLI create-tournament command."""
        from click.testing import CliRunner
        from evalarena.cli import main

        db_path = str(tmp_path / "test.db")
        runner = CliRunner()
        # Create models in the same DB
        runner.invoke(main, ["add-model", "cli-t-a", "--db", db_path])
        runner.invoke(main, ["add-model", "cli-t-b", "--db", db_path])

        result = runner.invoke(main, [
            "create-tournament", "CLI Tournament",
            "--models", "cli-t-a,cli-t-b",
            "--db", db_path,
        ])
        assert result.exit_code == 0
        assert "Tournament created" in result.output

    def test_cli_list_tournaments(self):
        """Test CLI list-tournaments command."""
        from click.testing import CliRunner
        from evalarena.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["list-tournaments", "--db", ":memory:"])
        assert result.exit_code == 0

    def test_cli_tournament_standings(self):
        """Test CLI tournament-standings command."""
        from click.testing import CliRunner
        from evalarena.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["tournament-standings", "fake-id", "--db", ":memory:"])
        assert result.exit_code == 0


# ── Battle Search Tests ────────────────────────────────────────────


class TestBattleSearch:
    """Tests for battle search functionality."""

    async def test_search_by_prompt(self, client: AsyncClient):
        """Search battles by prompt content."""
        a_id = await _register_model(client, "search-a")
        b_id = await _register_model(client, "search-b")
        await _create_battle(client, a_id, b_id, prompt="Explain quantum computing")
        await _create_battle(client, a_id, b_id, prompt="What is machine learning?")

        resp = await client.get("/api/battles/search?q=quantum")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert "quantum" in data[0]["prompt"].lower()

    async def test_search_by_response(self, client: AsyncClient):
        """Search battles by response content."""
        a_id = await _register_model(client, "resp-search-a")
        b_id = await _register_model(client, "resp-search-b")
        await client.post("/api/arena", json={
            "prompt": "Tell me about Python",
            "response_a": "Python is a versatile programming language",
            "response_b": "Python was created by Guido van Rossum",
            "model_a_id": a_id,
            "model_b_id": b_id,
        })

        resp = await client.get("/api/battles/search?q=Guido")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1

    async def test_search_no_results(self, client: AsyncClient):
        """Search with no matching content returns empty."""
        a_id = await _register_model(client, "no-search-a")
        b_id = await _register_model(client, "no-search-b")
        await _create_battle(client, a_id, b_id, prompt="Hello world")

        resp = await client.get("/api/battles/search?q=xyznonexistent")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_search_prompt_ranked_higher(self, client: AsyncClient):
        """Prompt matches have higher relevance than response matches."""
        a_id = await _register_model(client, "rank-a")
        b_id = await _register_model(client, "rank-b")
        # Battle with keyword in prompt
        await _create_battle(client, a_id, b_id, prompt="Python tutorial")
        # Battle with keyword only in response
        await client.post("/api/arena", json={
            "prompt": "Tell me about coding",
            "response_a": "Python is great for beginners",
            "response_b": "Java is also popular",
            "model_a_id": a_id,
            "model_b_id": b_id,
        })

        resp = await client.get("/api/battles/search?q=Python")
        data = resp.json()
        assert len(data) >= 1
        # Prompt match should have higher relevance
        assert data[0]["relevance_score"] >= data[-1]["relevance_score"]

    async def test_search_limit(self, client: AsyncClient):
        """Search respects limit parameter."""
        a_id = await _register_model(client, "limit-a")
        b_id = await _register_model(client, "limit-b")
        for i in range(5):
            await _create_battle(client, a_id, b_id, prompt=f"Python question {i}")

        resp = await client.get("/api/battles/search?q=Python&limit=2")
        data = resp.json()
        assert len(data) == 2


# ── Battle Search CLI Tests ────────────────────────────────────────


class TestBattleSearchCLI:
    """Tests for battle search CLI command."""

    def test_cli_search_battles(self):
        """Test CLI search-battles command."""
        from click.testing import CliRunner
        from evalarena.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["search-battles", "test", "--db", ":memory:"])
        assert result.exit_code == 0


# ── Win Streak Tests ───────────────────────────────────────────────


class TestWinStreaks:
    """Tests for win streak tracking."""

    async def test_win_streak_api(self, client: AsyncClient):
        """GET /api/streaks returns streak data."""
        a_id = await _register_model(client, "streak-a")
        b_id = await _register_model(client, "streak-b")

        # Create a winning streak for model A using direct DB to avoid random swap
        db: Database = client._transport.app.state.db  # type: ignore
        for i in range(3):
            battle = await db.create_battle(BattleCreate(
                prompt=f"Q{i}", response_a="a", response_b="b",
                model_a_id=a_id, model_b_id=b_id,
            ))
            await db.create_vote(
                VoteCreate(battle_id=battle.id, winner=Winner.MODEL_A)
            )

        resp = await client.get("/api/streaks")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 2

        # Find model A's streak
        streak_a = next(s for s in data if s["model_id"] == a_id)
        assert streak_a["current_streak"] == 3
        assert streak_a["current_streak_type"] == "win"
        assert streak_a["best_win_streak"] == 3

    async def test_loss_streak(self, client: AsyncClient):
        """Track loss streaks correctly."""
        a_id = await _register_model(client, "loss-a")
        b_id = await _register_model(client, "loss-b")

        db: Database = client._transport.app.state.db  # type: ignore
        # Model A loses all
        for i in range(3):
            battle = await db.create_battle(BattleCreate(
                prompt=f"Q{i}", response_a="a", response_b="b",
                model_a_id=a_id, model_b_id=b_id,
            ))
            await db.create_vote(
                VoteCreate(battle_id=battle.id, winner=Winner.MODEL_B)
            )

        resp = await client.get("/api/streaks")
        data = resp.json()
        streak_a = next(s for s in data if s["model_id"] == a_id)
        assert streak_a["current_streak"] == -3
        assert streak_a["current_streak_type"] == "loss"
        assert streak_a["best_loss_streak"] == 3

    async def test_mixed_streak(self, client: AsyncClient):
        """Track best streak across mixed results."""
        a_id = await _register_model(client, "mixed-a")
        b_id = await _register_model(client, "mixed-b")

        db: Database = client._transport.app.state.db  # type: ignore
        # Win, Win, Loss, Win, Win, Win (from model A's perspective)
        outcomes = [Winner.MODEL_A, Winner.MODEL_A, Winner.MODEL_B,
                    Winner.MODEL_A, Winner.MODEL_A, Winner.MODEL_A]
        for i, winner in enumerate(outcomes):
            battle = await db.create_battle(BattleCreate(
                prompt=f"Q{i}", response_a="a", response_b="b",
                model_a_id=a_id, model_b_id=b_id,
            ))
            await db.create_vote(VoteCreate(battle_id=battle.id, winner=winner))

        resp = await client.get("/api/streaks")
        data = resp.json()
        streak_a = next(s for s in data if s["model_id"] == a_id)
        assert streak_a["best_win_streak"] == 3  # Last 3 wins
        assert streak_a["current_streak"] == 3

    async def test_model_streak_api(self, client: AsyncClient):
        """GET /api/models/{id}/streak returns single model streak."""
        a_id = await _register_model(client, "single-streak-a")
        b_id = await _register_model(client, "single-streak-b")

        db: Database = client._transport.app.state.db  # type: ignore
        battle = await db.create_battle(BattleCreate(
            prompt="test", response_a="a", response_b="b",
            model_a_id=a_id, model_b_id=b_id,
        ))
        await db.create_vote(VoteCreate(battle_id=battle.id, winner=Winner.MODEL_A))

        resp = await client.get(f"/api/models/{a_id}/streak")
        assert resp.status_code == 200
        data = resp.json()
        assert data["model_id"] == a_id
        assert data["current_streak"] == 1

    async def test_model_streak_not_found(self, client: AsyncClient):
        """Streak for nonexistent model returns 404."""
        resp = await client.get("/api/models/nonexistent/streak")
        assert resp.status_code == 404

    async def test_no_battles_streak(self, client: AsyncClient):
        """Model with no battles has zero streak."""
        a_id = await _register_model(client, "no-streak")

        resp = await client.get(f"/api/models/{a_id}/streak")
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_streak"] == 0
        assert data["current_streak_type"] == "none"


# ── Win Streak CLI Tests ───────────────────────────────────────────


class TestWinStreakCLI:
    """Tests for win streak CLI command."""

    def test_cli_win_streaks(self):
        """Test CLI win-streaks command."""
        from click.testing import CliRunner
        from evalarena.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["win-streaks", "--db", ":memory:"])
        assert result.exit_code == 0


# ── Webhook Tests ──────────────────────────────────────────────────


class TestWebhooks:
    """Tests for webhook management."""

    async def test_create_webhook_api(self, client: AsyncClient):
        """POST /api/webhooks creates a webhook."""
        resp = await client.post("/api/webhooks", json={
            "url": "https://example.com/hook",
            "event": "vote",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["url"] == "https://example.com/hook"
        assert data["event"] == "vote"
        assert data["active"] is True

    async def test_list_webhooks_api(self, client: AsyncClient):
        """GET /api/webhooks lists webhooks."""
        await client.post("/api/webhooks", json={
            "url": "https://example.com/hook1",
            "event": "vote",
        })
        await client.post("/api/webhooks", json={
            "url": "https://example.com/hook2",
            "event": "battle",
        })

        resp = await client.get("/api/webhooks")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    async def test_list_webhooks_filter_event(self, client: AsyncClient):
        """GET /api/webhooks?event=vote filters by event."""
        await client.post("/api/webhooks", json={
            "url": "https://example.com/vote-hook",
            "event": "vote",
        })
        await client.post("/api/webhooks", json={
            "url": "https://example.com/battle-hook",
            "event": "battle",
        })

        resp = await client.get("/api/webhooks?event=vote")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["event"] == "vote"

    async def test_delete_webhook_api(self, client: AsyncClient):
        """DELETE /api/webhooks/{id} deletes a webhook."""
        create_resp = await client.post("/api/webhooks", json={
            "url": "https://example.com/to-delete",
            "event": "vote",
        })
        webhook_id = create_resp.json()["id"]

        resp = await client.delete(f"/api/webhooks/{webhook_id}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

        # Verify deleted
        list_resp = await client.get("/api/webhooks")
        assert len(list_resp.json()) == 0

    async def test_delete_nonexistent_webhook(self, client: AsyncClient):
        """Deleting nonexistent webhook returns 404."""
        resp = await client.delete("/api/webhooks/nonexistent")
        assert resp.status_code == 404


# ── Webhook DB Tests ───────────────────────────────────────────────


class TestWebhookDB:
    """Tests for webhook database operations."""

    async def test_create_webhook_db(self, db: Database):
        """Create webhook at DB level."""
        result = await db.create_webhook(
            url="https://example.com/hook", event="vote", secret="mysecret"
        )
        assert result["url"] == "https://example.com/hook"
        assert result["event"] == "vote"
        assert result["active"] is True

    async def test_get_active_webhooks(self, db: Database):
        """Get active webhooks for an event."""
        await db.create_webhook(url="https://example.com/active", event="vote")
        wh2 = await db.create_webhook(url="https://example.com/inactive", event="vote")
        await db.deactivate_webhook(wh2["id"])

        active = await db.get_active_webhooks("vote")
        assert len(active) == 1
        assert active[0]["url"] == "https://example.com/active"

    async def test_deactivate_webhook(self, db: Database):
        """Deactivate a webhook."""
        wh = await db.create_webhook(url="https://example.com/test", event="vote")
        assert await db.deactivate_webhook(wh["id"]) is True

        webhooks = await db.list_webhooks()
        assert len(webhooks) == 1
        assert webhooks[0]["active"] is False

    async def test_delete_webhook_db(self, db: Database):
        """Delete a webhook at DB level."""
        wh = await db.create_webhook(url="https://example.com/del", event="vote")
        assert await db.delete_webhook(wh["id"]) is True
        assert await db.list_webhooks() == []

    async def test_webhook_with_secret(self, db: Database):
        """Webhook with secret stores it."""
        wh = await db.create_webhook(
            url="https://example.com/secret", event="vote", secret="hmac_key"
        )
        active = await db.get_active_webhooks("vote")
        assert len(active) == 1
        assert active[0]["secret"] == "hmac_key"


# ── Webhook CLI Tests ──────────────────────────────────────────────


class TestWebhookCLI:
    """Tests for webhook CLI commands."""

    def test_cli_create_webhook(self):
        """Test CLI create-webhook command."""
        from click.testing import CliRunner
        from evalarena.cli import main

        runner = CliRunner()
        result = runner.invoke(main, [
            "create-webhook", "https://example.com/hook",
            "--event", "vote",
            "--db", ":memory:",
        ])
        assert result.exit_code == 0
        assert "Webhook created" in result.output

    def test_cli_list_webhooks(self):
        """Test CLI list-webhooks command."""
        from click.testing import CliRunner
        from evalarena.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["list-webhooks", "--db", ":memory:"])
        assert result.exit_code == 0


# ── Backup/Restore Tests ───────────────────────────────────────────


class TestBackupRestore:
    """Tests for database backup and restore."""

    def test_cli_backup(self, tmp_path):
        """Test CLI backup command."""
        import os
        from click.testing import CliRunner
        from evalarena.cli import main

        db_path = str(tmp_path / "test.db")
        backup_path = str(tmp_path / "backup.json")

        runner = CliRunner()
        # Create a model first
        runner.invoke(main, ["add-model", "backup-test", "--db", db_path])

        result = runner.invoke(main, ["backup", "--output", backup_path, "--db", db_path])
        assert result.exit_code == 0
        assert os.path.exists(backup_path)

        # Verify backup content
        with open(backup_path) as f:
            data = json.load(f)
        assert "models" in data
        assert "battles" in data
        assert "prompt_templates" in data
        assert len(data["models"]) >= 1

    def test_cli_restore(self, tmp_path):
        """Test CLI restore command."""
        import os
        from click.testing import CliRunner
        from evalarena.cli import main

        db1_path = str(tmp_path / "source.db")
        db2_path = str(tmp_path / "target.db")
        backup_path = str(tmp_path / "backup.json")

        runner = CliRunner()
        # Create data in source
        runner.invoke(main, ["add-model", "restore-test", "--category", "coding", "--db", db1_path])
        runner.invoke(main, ["backup", "--output", backup_path, "--db", db1_path])

        # Restore to target
        result = runner.invoke(main, ["restore", backup_path, "--db", db2_path, "--yes"])
        assert result.exit_code == 0
        assert "Models restored: 1" in result.output

    def test_cli_restore_skips_duplicates(self, tmp_path):
        """Restore skips models that already exist."""
        from click.testing import CliRunner
        from evalarena.cli import main

        db_path = str(tmp_path / "test.db")
        backup_path = str(tmp_path / "backup.json")

        runner = CliRunner()
        runner.invoke(main, ["add-model", "dup-test", "--db", db_path])
        runner.invoke(main, ["backup", "--output", backup_path, "--db", db_path])

        # Restore to same DB (should skip)
        result = runner.invoke(main, ["restore", backup_path, "--db", db_path, "--yes"])
        assert result.exit_code == 0
        assert "Models restored: 0" in result.output


# ── Webhook Notification Integration ───────────────────────────────


class TestWebhookNotification:
    """Test webhook module imports and basic functionality."""

    def test_webhook_module_import(self):
        """Webhook module can be imported."""
        from evalarena.webhooks import dispatch_webhook, fire_webhooks
        assert callable(dispatch_webhook)
        assert callable(fire_webhooks)

    async def test_webhook_fires_on_vote(self, client: AsyncClient):
        """Voting triggers webhook dispatch (we can't verify delivery,
        but we verify the vote still succeeds with webhooks registered)."""
        # Register a webhook (pointing to a non-existent URL is fine for testing)
        await client.post("/api/webhooks", json={
            "url": "https://localhost:1/nonexistent",
            "event": "vote",
        })

        # Create and vote on a battle
        a_id = await _register_model(client, "wh-vote-a")
        b_id = await _register_model(client, "wh-vote-b")
        bid = await _create_battle(client, a_id, b_id)

        resp = await client.post("/api/vote", json={
            "battle_id": bid,
            "winner": "model_a",
        })
        # Vote should succeed even if webhook delivery fails
        assert resp.status_code == 201


# ── Full-text Search DB Tests ──────────────────────────────────────


class TestBattleSearchDB:
    """Tests for battle search at database level."""

    async def test_search_prompt_match(self, db: Database):
        """Search finds battles by prompt content."""
        m1 = await db.create_model(ModelCreate(name="s-db-a"))
        m2 = await db.create_model(ModelCreate(name="s-db-b"))
        await db.create_battle(BattleCreate(
            prompt="Explain neural networks", response_a="a", response_b="b",
            model_a_id=m1.id, model_b_id=m2.id,
        ))
        await db.create_battle(BattleCreate(
            prompt="What is Python?", response_a="a", response_b="b",
            model_a_id=m1.id, model_b_id=m2.id,
        ))

        results = await db.search_battles("neural")
        assert len(results) == 1
        assert "neural" in results[0]["prompt"].lower()

    async def test_search_response_match(self, db: Database):
        """Search finds battles by response content."""
        m1 = await db.create_model(ModelCreate(name="s-resp-a"))
        m2 = await db.create_model(ModelCreate(name="s-resp-b"))
        await db.create_battle(BattleCreate(
            prompt="Tell me about coding",
            response_a="Python is a great language",
            response_b="Java is also popular",
            model_a_id=m1.id, model_b_id=m2.id,
        ))

        results = await db.search_battles("Python")
        assert len(results) >= 1
