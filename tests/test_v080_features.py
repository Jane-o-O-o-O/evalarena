"""Tests for v0.8.0 features: model tags, rating decay, CORS middleware,
dashboard analytics, and CLI commands."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from evalarena.app import create_app
from evalarena.db.database import Database
from evalarena.db.models import (
    BattleCreate,
    ModelCreate,
    TagCreate,
    VoteCreate,
    Winner,
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


# ── Tag DB Tests ───────────────────────────────────────────────────


class TestTagDB:
    """Tests for tag database operations."""

    async def test_create_tag(self, db: Database):
        """Test creating a tag."""
        tag = await db.create_tag("open-source", "#22c55e")
        assert tag["name"] == "open-source"
        assert tag["color"] == "#22c55e"
        assert tag["model_count"] == 0
        assert "id" in tag

    async def test_create_tag_default_color(self, db: Database):
        """Test creating a tag with default color."""
        tag = await db.create_tag("test-tag")
        assert tag["color"] == "#6366f1"

    async def test_get_tag(self, db: Database):
        """Test getting a tag by ID."""
        created = await db.create_tag("coding-strong")
        tag = await db.get_tag(created["id"])
        assert tag is not None
        assert tag["name"] == "coding-strong"

    async def test_get_tag_by_name(self, db: Database):
        """Test getting a tag by name."""
        await db.create_tag("fine-tuned")
        tag = await db.get_tag_by_name("fine-tuned")
        assert tag is not None
        assert tag["name"] == "fine-tuned"

    async def test_get_nonexistent_tag(self, db: Database):
        """Getting nonexistent tag returns None."""
        assert await db.get_tag("nonexistent") is None
        assert await db.get_tag_by_name("nonexistent") is None

    async def test_list_tags(self, db: Database):
        """Test listing all tags."""
        await db.create_tag("alpha")
        await db.create_tag("beta")
        await db.create_tag("gamma")
        tags = await db.list_tags()
        assert len(tags) == 3
        names = [t["name"] for t in tags]
        assert "alpha" in names
        assert "beta" in names

    async def test_list_tags_empty(self, db: Database):
        """Listing tags on empty DB returns empty list."""
        tags = await db.list_tags()
        assert tags == []

    async def test_update_tag(self, db: Database):
        """Test updating a tag."""
        tag = await db.create_tag("old-name", "#ff0000")
        updated = await db.update_tag(tag["id"], name="new-name", color="#00ff00")
        assert updated is not None
        assert updated["name"] == "new-name"
        assert updated["color"] == "#00ff00"

    async def test_update_tag_partial(self, db: Database):
        """Test partial update of a tag."""
        tag = await db.create_tag("keep-name", "#ff0000")
        updated = await db.update_tag(tag["id"], color="#00ff00")
        assert updated["name"] == "keep-name"
        assert updated["color"] == "#00ff00"

    async def test_update_nonexistent_tag(self, db: Database):
        """Updating nonexistent tag returns None."""
        result = await db.update_tag("nonexistent", name="new")
        assert result is None

    async def test_delete_tag(self, db: Database):
        """Test deleting a tag."""
        tag = await db.create_tag("to-delete")
        deleted = await db.delete_tag(tag["id"])
        assert deleted is True
        assert await db.get_tag(tag["id"]) is None

    async def test_delete_nonexistent_tag(self, db: Database):
        """Deleting nonexistent tag returns False."""
        assert await db.delete_tag("nonexistent") is False

    async def test_add_model_tag(self, db: Database):
        """Test associating a tag with a model."""
        model = await db.create_model(ModelCreate(name="tagged-model"))
        tag = await db.create_tag("my-tag")
        result = await db.add_model_tag(model.id, tag["id"])
        assert result is True

    async def test_add_model_tag_duplicate(self, db: Database):
        """Adding same tag twice returns False."""
        model = await db.create_model(ModelCreate(name="dup-tag-model"))
        tag = await db.create_tag("dup-tag")
        await db.add_model_tag(model.id, tag["id"])
        result = await db.add_model_tag(model.id, tag["id"])
        assert result is False

    async def test_add_model_tag_invalid_model(self, db: Database):
        """Adding tag to nonexistent model raises ValueError."""
        tag = await db.create_tag("orphan-tag")
        with pytest.raises(ValueError, match="not found"):
            await db.add_model_tag("nonexistent", tag["id"])

    async def test_add_model_tag_invalid_tag(self, db: Database):
        """Adding nonexistent tag to model raises ValueError."""
        model = await db.create_model(ModelCreate(name="no-tag-model"))
        with pytest.raises(ValueError, match="not found"):
            await db.add_model_tag(model.id, "nonexistent")

    async def test_remove_model_tag(self, db: Database):
        """Test removing a tag from a model."""
        model = await db.create_model(ModelCreate(name="untag-model"))
        tag = await db.create_tag("remove-me")
        await db.add_model_tag(model.id, tag["id"])
        result = await db.remove_model_tag(model.id, tag["id"])
        assert result is True
        tags = await db.get_model_tags(model.id)
        assert len(tags) == 0

    async def test_get_model_tags(self, db: Database):
        """Test getting tags for a model."""
        model = await db.create_model(ModelCreate(name="multi-tag-model"))
        tag1 = await db.create_tag("tag-a")
        tag2 = await db.create_tag("tag-b")
        await db.add_model_tag(model.id, tag1["id"])
        await db.add_model_tag(model.id, tag2["id"])
        tags = await db.get_model_tags(model.id)
        assert len(tags) == 2
        names = [t["name"] for t in tags]
        assert "tag-a" in names
        assert "tag-b" in names

    async def test_get_model_tags_empty(self, db: Database):
        """Getting tags for model with no tags returns empty."""
        model = await db.create_model(ModelCreate(name="no-tags"))
        tags = await db.get_model_tags(model.id)
        assert tags == []

    async def test_get_models_by_tag(self, db: Database):
        """Test getting models by tag."""
        m1 = await db.create_model(ModelCreate(name="model-x"))
        m2 = await db.create_model(ModelCreate(name="model-y"))
        tag = await db.create_tag("group-tag")
        await db.add_model_tag(m1.id, tag["id"])
        await db.add_model_tag(m2.id, tag["id"])
        models = await db.get_models_by_tag(tag["id"])
        assert len(models) == 2
        names = [m.name for m in models]
        assert "model-x" in names
        assert "model-y" in names

    async def test_delete_tag_cascades(self, db: Database):
        """Deleting a tag removes all model associations."""
        model = await db.create_model(ModelCreate(name="cascade-model"))
        tag = await db.create_tag("cascade-tag")
        await db.add_model_tag(model.id, tag["id"])
        await db.delete_tag(tag["id"])
        tags = await db.get_model_tags(model.id)
        assert len(tags) == 0

    async def test_tag_model_count(self, db: Database):
        """Tag model count updates correctly."""
        tag = await db.create_tag("counted")
        m1 = await db.create_model(ModelCreate(name="c1"))
        m2 = await db.create_model(ModelCreate(name="c2"))
        await db.add_model_tag(m1.id, tag["id"])
        await db.add_model_tag(m2.id, tag["id"])
        refreshed = await db.get_tag(tag["id"])
        assert refreshed["model_count"] == 2


# ── Tag API Tests ──────────────────────────────────────────────────


class TestTagAPI:
    """Tests for tag API endpoints."""

    async def test_create_tag_api(self, client: AsyncClient):
        """POST /api/tags creates a tag."""
        resp = await client.post("/api/tags", json={"name": "api-tag", "color": "#ff0000"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "api-tag"
        assert data["color"] == "#ff0000"

    async def test_create_tag_duplicate(self, client: AsyncClient):
        """Creating duplicate tag returns 409."""
        await client.post("/api/tags", json={"name": "dup-api"})
        resp = await client.post("/api/tags", json={"name": "dup-api"})
        assert resp.status_code == 409

    async def test_list_tags_api(self, client: AsyncClient):
        """GET /api/tags lists all tags."""
        await client.post("/api/tags", json={"name": "listed-a"})
        await client.post("/api/tags", json={"name": "listed-b"})
        resp = await client.get("/api/tags")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 2

    async def test_get_tag_api(self, client: AsyncClient):
        """GET /api/tags/{id} returns tag details."""
        create_resp = await client.post("/api/tags", json={"name": "get-me"})
        tag_id = create_resp.json()["id"]
        resp = await client.get(f"/api/tags/{tag_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "get-me"

    async def test_get_tag_not_found(self, client: AsyncClient):
        """GET /api/tags/{id} for nonexistent returns 404."""
        resp = await client.get("/api/tags/nonexistent")
        assert resp.status_code == 404

    async def test_update_tag_api(self, client: AsyncClient):
        """PUT /api/tags/{id} updates a tag."""
        create_resp = await client.post("/api/tags", json={"name": "update-me"})
        tag_id = create_resp.json()["id"]
        resp = await client.put(f"/api/tags/{tag_id}", json={"name": "updated", "color": "#00ff00"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "updated"
        assert resp.json()["color"] == "#00ff00"

    async def test_delete_tag_api(self, client: AsyncClient):
        """DELETE /api/tags/{id} deletes a tag."""
        create_resp = await client.post("/api/tags", json={"name": "delete-api"})
        tag_id = create_resp.json()["id"]
        resp = await client.delete(f"/api/tags/{tag_id}")
        assert resp.status_code == 200
        # Verify deleted
        resp = await client.get(f"/api/tags/{tag_id}")
        assert resp.status_code == 404

    async def test_delete_tag_not_found(self, client: AsyncClient):
        """DELETE /api/tags/{id} for nonexistent returns 404."""
        resp = await client.delete("/api/tags/nonexistent")
        assert resp.status_code == 404

    async def test_add_tag_to_model_api(self, client: AsyncClient):
        """POST /api/tags/{id}/models/{id} associates tag with model."""
        model_id = await _register_model(client, "api-tag-model")
        create_resp = await client.post("/api/tags", json={"name": "model-tag"})
        tag_id = create_resp.json()["id"]
        resp = await client.post(f"/api/tags/{tag_id}/models/{model_id}")
        assert resp.status_code == 200

    async def test_add_tag_to_model_not_found(self, client: AsyncClient):
        """Adding tag to nonexistent model returns 404."""
        create_resp = await client.post("/api/tags", json={"name": "orphan"})
        tag_id = create_resp.json()["id"]
        resp = await client.post(f"/api/tags/{tag_id}/models/nonexistent")
        assert resp.status_code == 404

    async def test_remove_tag_from_model_api(self, client: AsyncClient):
        """DELETE /api/tags/{id}/models/{id} removes tag from model."""
        model_id = await _register_model(client, "untag-api-model")
        create_resp = await client.post("/api/tags", json={"name": "remove-api"})
        tag_id = create_resp.json()["id"]
        await client.post(f"/api/tags/{tag_id}/models/{model_id}")
        resp = await client.delete(f"/api/tags/{tag_id}/models/{model_id}")
        assert resp.status_code == 200

    async def test_list_models_by_tag_api(self, client: AsyncClient):
        """GET /api/tags/{id}/models lists models with tag."""
        m1_id = await _register_model(client, "tagged-1")
        m2_id = await _register_model(client, "tagged-2")
        create_resp = await client.post("/api/tags", json={"name": "group"})
        tag_id = create_resp.json()["id"]
        await client.post(f"/api/tags/{tag_id}/models/{m1_id}")
        await client.post(f"/api/tags/{tag_id}/models/{m2_id}")
        resp = await client.get(f"/api/tags/{tag_id}/models")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    async def test_list_models_by_tag_not_found(self, client: AsyncClient):
        """Listing models by nonexistent tag returns 404."""
        resp = await client.get("/api/tags/nonexistent/models")
        assert resp.status_code == 404


# ── Tag CLI Tests ──────────────────────────────────────────────────


class TestTagCLI:
    """Tests for tag CLI commands."""

    def test_cli_create_tag(self, tmp_path):
        """Test CLI create-tag command."""
        from click.testing import CliRunner
        from evalarena.cli import main

        db_path = str(tmp_path / "test.db")
        runner = CliRunner()
        result = runner.invoke(main, ["create-tag", "cli-tag", "--color", "#ff0000", "--db", db_path])
        assert result.exit_code == 0
        assert "Tag created" in result.output

    def test_cli_create_tag_duplicate(self, tmp_path):
        """Test creating duplicate tag via CLI."""
        from click.testing import CliRunner
        from evalarena.cli import main

        db_path = str(tmp_path / "test.db")
        runner = CliRunner()
        runner.invoke(main, ["create-tag", "dup-cli", "--db", db_path])
        result = runner.invoke(main, ["create-tag", "dup-cli", "--db", db_path])
        assert "already exists" in result.output

    def test_cli_list_tags(self, tmp_path):
        """Test CLI list-tags command."""
        from click.testing import CliRunner
        from evalarena.cli import main

        db_path = str(tmp_path / "test.db")
        runner = CliRunner()
        runner.invoke(main, ["create-tag", "tag-a", "--db", db_path])
        runner.invoke(main, ["create-tag", "tag-b", "--db", db_path])
        result = runner.invoke(main, ["list-tags", "--db", db_path])
        assert result.exit_code == 0
        assert "tag-a" in result.output
        assert "tag-b" in result.output

    def test_cli_list_tags_empty(self):
        """Test CLI list-tags on empty DB."""
        from click.testing import CliRunner
        from evalarena.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["list-tags", "--db", ":memory:"])
        assert result.exit_code == 0
        assert "No tags found" in result.output

    def test_cli_tag_model(self, tmp_path):
        """Test CLI tag-model command."""
        from click.testing import CliRunner
        from evalarena.cli import main

        db_path = str(tmp_path / "test.db")
        runner = CliRunner()
        runner.invoke(main, ["add-model", "my-model", "--db", db_path])
        runner.invoke(main, ["create-tag", "my-tag", "--db", db_path])
        result = runner.invoke(main, ["tag-model", "my-model", "my-tag", "--db", db_path])
        assert result.exit_code == 0
        assert "Tagged" in result.output

    def test_cli_tag_model_not_found(self, tmp_path):
        """Test CLI tag-model with nonexistent model."""
        from click.testing import CliRunner
        from evalarena.cli import main

        db_path = str(tmp_path / "test.db")
        runner = CliRunner()
        runner.invoke(main, ["create-tag", "orphan", "--db", db_path])
        result = runner.invoke(main, ["tag-model", "ghost", "orphan", "--db", db_path])
        assert "not found" in result.output

    def test_cli_untag_model(self, tmp_path):
        """Test CLI untag-model command."""
        from click.testing import CliRunner
        from evalarena.cli import main

        db_path = str(tmp_path / "test.db")
        runner = CliRunner()
        runner.invoke(main, ["add-model", "untag-m", "--db", db_path])
        runner.invoke(main, ["create-tag", "untag-t", "--db", db_path])
        runner.invoke(main, ["tag-model", "untag-m", "untag-t", "--db", db_path])
        result = runner.invoke(main, ["untag-model", "untag-m", "untag-t", "--db", db_path])
        assert result.exit_code == 0
        assert "Removed" in result.output

    def test_cli_delete_tag(self, tmp_path):
        """Test CLI delete-tag command."""
        from click.testing import CliRunner
        from evalarena.cli import main

        db_path = str(tmp_path / "test.db")
        runner = CliRunner()
        runner.invoke(main, ["create-tag", "del-tag", "--db", db_path])
        result = runner.invoke(main, ["delete-tag", "del-tag", "--yes", "--db", db_path])
        assert result.exit_code == 0
        assert "Deleted" in result.output

    def test_cli_delete_tag_not_found(self):
        """Test CLI delete-tag with nonexistent tag."""
        from click.testing import CliRunner
        from evalarena.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["delete-tag", "ghost-tag", "--db", ":memory:"])
        assert "not found" in result.output


# ── Rating Decay Tests ─────────────────────────────────────────────


class TestRatingDecay:
    """Tests for rating decay functionality."""

    async def test_apply_decay_no_models(self, db: Database):
        """Applying decay to empty DB returns no changes."""
        result = await db.apply_rating_decay()
        assert result["models_affected"] == 0
        assert result["total_rating_decayed"] == 0.0

    async def test_apply_decay_active_models_untouched(self, db: Database):
        """Models with recent battles are not decayed."""
        m1 = await db.create_model(ModelCreate(name="active-model"))
        m2 = await db.create_model(ModelCreate(name="opponent"))

        # Create and vote on a battle (makes models active)
        battle = await db.create_battle(BattleCreate(
            prompt="test", response_a="a", response_b="b",
            model_a_id=m1.id, model_b_id=m2.id,
        ))
        await db.create_vote(VoteCreate(battle_id=battle.id, winner=Winner.MODEL_A))

        result = await db.apply_rating_decay(inactive_days=1)
        assert result["models_affected"] == 0

    async def test_apply_decay_inactive_models_decayed(self, db: Database):
        """Models without recent battles get rating decayed."""
        # Create a model but don't give it any battles
        m = await db.create_model(ModelCreate(name="stale-model"))
        # Override creation date to be old
        from datetime import datetime, timezone, timedelta
        old_date = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        await db.db.execute(
            "UPDATE models SET created_at = ? WHERE id = ?", (old_date, m.id)
        )
        await db.db.commit()

        result = await db.apply_rating_decay(inactive_days=30, decay_rate=0.02)
        assert result["models_affected"] >= 1
        assert result["total_rating_decayed"] > 0

        # Verify rating decreased
        updated = await db.get_model(m.id)
        assert updated is not None
        assert updated.rating < 1000.0

    async def test_apply_decay_min_rating_floor(self, db: Database):
        """Rating decay respects minimum rating floor."""
        m = await db.create_model(ModelCreate(name="floor-model"))
        # Set rating to minimum
        await db.db.execute("UPDATE models SET rating = ? WHERE id = ?", (100.0, m.id))
        await db.db.commit()

        result = await db.apply_rating_decay(min_rating=100.0)
        assert result["models_affected"] == 0

        # Verify rating unchanged
        updated = await db.get_model(m.id)
        assert updated.rating == 100.0

    async def test_apply_decay_api(self, client: AsyncClient):
        """POST /api/dashboard/apply-decay applies decay."""
        resp = await client.post("/api/dashboard/apply-decay", json={
            "inactive_days": 30, "decay_rate": 0.02, "min_rating": 100.0,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "models_affected" in data
        assert "total_rating_decayed" in data
        assert "details" in data


# ── Dashboard Analytics Tests ──────────────────────────────────────


class TestDashboardAnalytics:
    """Tests for dashboard analytics API."""

    async def test_rating_distribution_empty(self, client: AsyncClient):
        """Rating distribution on empty DB returns zero."""
        resp = await client.get("/api/dashboard/rating-distribution")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_models"] == 0
        assert data["mean_rating"] == 0.0

    async def test_rating_distribution_with_models(self, client: AsyncClient):
        """Rating distribution with models returns histogram."""
        await _register_model(client, "dist-a")
        await _register_model(client, "dist-b")
        resp = await client.get("/api/dashboard/rating-distribution")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_models"] == 2
        assert data["mean_rating"] == 1000.0
        assert data["median_rating"] == 1000.0
        assert len(data["buckets"]) > 0

    async def test_activity_trends(self, client: AsyncClient):
        """Activity trends returns daily data."""
        resp = await client.get("/api/dashboard/activity-trends?days=7")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 7
        for d in data:
            assert "date" in d
            assert "battles" in d
            assert "votes" in d

    async def test_activity_trends_with_battles(self, client: AsyncClient):
        """Activity trends counts battles correctly."""
        a_id = await _register_model(client, "trend-a")
        b_id = await _register_model(client, "trend-b")
        await _create_battle(client, a_id, b_id, "trend test")

        resp = await client.get("/api/dashboard/activity-trends?days=1")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["battles"] >= 1

    async def test_top_movers_empty(self, client: AsyncClient):
        """Top movers on empty DB returns empty lists."""
        resp = await client.get("/api/dashboard/top-movers?days=7")
        assert resp.status_code == 200
        data = resp.json()
        assert data["top_gainers"] == []
        assert data["top_losers"] == []

    async def test_top_movers_with_battles(self, client: AsyncClient):
        """Top movers shows rating changes after battles."""
        a_id = await _register_model(client, "mover-a")
        b_id = await _register_model(client, "mover-b")
        battle_id = await _create_battle(client, a_id, b_id, "mover test")
        await _vote_battle(client, battle_id, "model_a")

        resp = await client.get("/api/dashboard/top-movers?days=7")
        assert resp.status_code == 200
        data = resp.json()
        # model_a should be a gainer
        assert len(data["top_gainers"]) >= 1

    async def test_full_dashboard_stats(self, client: AsyncClient):
        """GET /api/dashboard/stats returns full analytics."""
        a_id = await _register_model(client, "dash-a")
        b_id = await _register_model(client, "dash-b")
        battle_id = await _create_battle(client, a_id, b_id, "dashboard test")
        await _vote_battle(client, battle_id, "model_a")

        resp = await client.get("/api/dashboard/stats?period_days=7")
        assert resp.status_code == 200
        data = resp.json()
        assert "rating_distribution" in data
        assert "activity_trends" in data
        assert "top_gainers" in data
        assert "top_losers" in data
        assert data["period_days"] == 7


# ── Dashboard CLI Tests ────────────────────────────────────────────


class TestDashboardCLI:
    """Tests for dashboard CLI commands."""

    def test_cli_dashboard_stats(self):
        """Test CLI dashboard-stats command."""
        from click.testing import CliRunner
        from evalarena.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["dashboard-stats", "--db", ":memory:"])
        assert result.exit_code == 0
        assert "Rating Distribution" in result.output

    def test_cli_apply_decay(self):
        """Test CLI apply-decay command."""
        from click.testing import CliRunner
        from evalarena.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["apply-decay", "--db", ":memory:"])
        assert result.exit_code == 0
        assert "Rating Decay Applied" in result.output

    def test_cli_apply_decay_with_models(self, tmp_path):
        """Test CLI apply-decay with actual models."""
        from click.testing import CliRunner
        from evalarena.cli import main

        db_path = str(tmp_path / "test.db")
        runner = CliRunner()
        runner.invoke(main, ["add-model", "decay-test", "--db", db_path])
        result = runner.invoke(main, [
            "apply-decay", "--inactive-days", "1",
            "--decay-rate", "0.05", "--db", db_path,
        ])
        assert result.exit_code == 0
        assert "Rating Decay Applied" in result.output


# ── CORS Middleware Tests ──────────────────────────────────────────


class TestCORSMiddleware:
    """Tests for CORS middleware."""

    async def test_cors_headers_present(self, client: AsyncClient):
        """CORS headers are present on API responses."""
        resp = await client.options(
            "/api/models",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        # CORS middleware should handle this
        assert resp.status_code in (200, 204)

    async def test_cors_allows_get(self, client: AsyncClient):
        """GET requests work with CORS origin header."""
        resp = await client.get(
            "/api/models",
            headers={"Origin": "http://localhost:3000"},
        )
        assert resp.status_code == 200

    async def test_cors_custom_origins(self):
        """App with custom CORS origins works."""
        app = create_app(in_memory=True, cors_origins=["http://example.com"])
        db: Database = app.state.db
        await db.connect()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/api/models")
            assert resp.status_code == 200
        await db.close()
