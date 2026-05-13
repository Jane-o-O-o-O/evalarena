"""Tests for v0.6.0 features: seed templates, vote comments in battles,
comparison matrix, category stats, battles-with-comments API, and CLI commands."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from evalarena.app import create_app
from evalarena.db.database import Database
from evalarena.db.models import (
    BattleCreate,
    ModelCreate,
    VoteCreate,
    Winner,
)
from evalarena.seed_templates import (
    get_seed_templates,
    get_seed_templates_by_category,
    SEED_TEMPLATES,
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


async def _setup_battle_with_vote(
    client: AsyncClient,
    vote_winner: str = "model_a",
    comment: str = "Test comment",
) -> tuple[str, str, str]:
    """Helper: create two models, a battle, and vote. Returns (model_a_id, model_b_id, battle_id)."""
    resp_a = await client.post("/api/models", json={"name": "alpha-model"})
    resp_b = await client.post("/api/models", json={"name": "beta-model"})
    model_a_id = resp_a.json()["id"]
    model_b_id = resp_b.json()["id"]

    battle_resp = await client.post("/api/arena", json={
        "prompt": "What is 2+2?",
        "response_a": "4",
        "response_b": "Four",
        "model_a_id": model_a_id,
        "model_b_id": model_b_id,
    })
    battle_id = battle_resp.json()["id"]

    await client.post("/api/vote", json={
        "battle_id": battle_id,
        "winner": vote_winner,
        "comment": comment,
    })
    return model_a_id, model_b_id, battle_id


# ── Seed Templates Module ─────────────────────────────────────────


class TestSeedTemplates:
    """Tests for the built-in seed template data."""

    def test_seed_templates_exist(self):
        """Verify seed templates are defined."""
        templates = get_seed_templates()
        assert len(templates) >= 15  # Should have 16 templates

    def test_seed_templates_have_required_fields(self):
        """Every seed template has all required fields."""
        for t in SEED_TEMPLATES:
            assert "name" in t
            assert "prompt_text" in t
            assert "category" in t
            assert len(t["name"]) > 0
            assert len(t["prompt_text"]) > 0
            assert len(t["category"]) > 0

    def test_seed_templates_categories(self):
        """Seed templates cover expected categories."""
        categories = {t["category"] for t in SEED_TEMPLATES}
        expected = {"coding", "writing", "reasoning", "math", "general"}
        assert expected.issubset(categories)

    def test_filter_by_category(self):
        """Category filter returns only matching templates."""
        coding = get_seed_templates_by_category("coding")
        assert len(coding) >= 3
        for t in coding:
            assert t["category"] == "coding"

    def test_filter_nonexistent_category(self):
        """Filtering by nonexistent category returns empty list."""
        result = get_seed_templates_by_category("nonexistent")
        assert result == []

    def test_unique_names(self):
        """All seed template names are unique."""
        names = [t["name"] for t in SEED_TEMPLATES]
        assert len(names) == len(set(names))


# ── Seed Templates DB ─────────────────────────────────────────────


class TestSeedTemplatesDB:
    """Tests for seeding templates in the database."""

    async def test_seed_templates_bulk_insert(self, db: Database):
        """Test bulk insert of seed templates."""
        templates = get_seed_templates()
        added, skipped = await db.seed_prompt_templates(templates)
        assert added == len(templates)
        assert skipped == 0

    async def test_seed_templates_skip_duplicates(self, db: Database):
        """Running seed twice skips duplicates."""
        templates = get_seed_templates()
        added1, skipped1 = await db.seed_prompt_templates(templates)
        assert added1 > 0
        assert skipped1 == 0

        added2, skipped2 = await db.seed_prompt_templates(templates)
        assert added2 == 0
        assert skipped2 == len(templates)

    async def test_seed_templates_partial_category(self, db: Database):
        """Seed only coding templates."""
        coding = get_seed_templates_by_category("coding")
        added, skipped = await db.seed_prompt_templates(coding)
        assert added == len(coding)
        assert skipped == 0

        # Verify only coding templates exist
        all_templates = await db.list_prompt_templates()
        for t in all_templates:
            assert t.category == "coding"


# ── Seed Templates CLI ────────────────────────────────────────────


class TestSeedTemplatesCLI:
    """Tests for the seed-templates CLI command."""

    def test_cli_seed_templates(self):
        """Test CLI seed-templates command."""
        from click.testing import CliRunner
        from evalarena.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["seed-templates", "--db", ":memory:"])
        assert result.exit_code == 0
        assert "added" in result.output.lower() or "seed" in result.output.lower()

    def test_cli_seed_templates_category(self):
        """Test CLI seed-templates with category filter."""
        from click.testing import CliRunner
        from evalarena.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["seed-templates", "--db", ":memory:", "--category", "coding"])
        assert result.exit_code == 0


# ── Vote Comments in Battles ──────────────────────────────────────


class TestBattlesWithComments:
    """Tests for getting battles with vote comments."""

    async def test_battles_with_comments_api(self, client: AsyncClient):
        """Test GET /api/battles/with-comments."""
        await _setup_battle_with_vote(client, comment="Model A had better reasoning")

        resp = await client.get("/api/battles/with-comments")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1

        # Find our battle
        battle = data[0]
        assert "comments" in battle
        assert "model_a_name" in battle
        assert "model_b_name" in battle
        assert "winner" in battle

    async def test_battles_with_comments_empty(self, client: AsyncClient):
        """Battles with comments returns empty when no battles."""
        resp = await client.get("/api/battles/with-comments")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_vote_comment_appears(self, client: AsyncClient):
        """Vote comment appears in battle details."""
        comment_text = "Great explanation of recursion"
        await _setup_battle_with_vote(client, comment=comment_text)

        resp = await client.get("/api/battles/with-comments")
        data = resp.json()
        assert len(data) >= 1

        battle = data[0]
        assert len(battle["comments"]) >= 1
        assert battle["comments"][0]["comment"] == comment_text

    async def test_battle_no_comments(self, client: AsyncClient):
        """Battle voted without comment shows empty comments."""
        await _setup_battle_with_vote(client, comment="")

        resp = await client.get("/api/battles/with-comments")
        data = resp.json()
        assert len(data) >= 1
        # Empty comments should not appear in the comments list
        battle = data[0]
        assert battle["comments"] == []

    async def test_battles_with_comments_pagination(self, client: AsyncClient):
        """Test pagination for battles with comments."""
        # Create multiple battles
        for i in range(5):
            resp_a = await client.post("/api/models", json={"name": f"model-a-{i}"})
            resp_b = await client.post("/api/models", json={"name": f"model-b-{i}"})
            battle_resp = await client.post("/api/arena", json={
                "prompt": f"Question {i}",
                "response_a": "A",
                "response_b": "B",
                "model_a_id": resp_a.json()["id"],
                "model_b_id": resp_b.json()["id"],
            })
            await client.post("/api/vote", json={
                "battle_id": battle_resp.json()["id"],
                "winner": "model_a",
                "comment": f"Comment {i}",
            })

        # Test pagination
        resp = await client.get("/api/battles/with-comments?limit=2&offset=0")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) <= 2

        resp2 = await client.get("/api/battles/with-comments?limit=2&offset=2")
        assert resp2.status_code == 200


# ── Comparison Matrix ─────────────────────────────────────────────


class TestComparisonMatrix:
    """Tests for the model comparison matrix."""

    async def test_comparison_matrix_api(self, client: AsyncClient):
        """Test GET /api/stats/comparison-matrix."""
        await _setup_battle_with_vote(client)

        resp = await client.get("/api/stats/comparison-matrix")
        assert resp.status_code == 200
        data = resp.json()
        assert "models" in data
        assert "matrix" in data
        assert len(data["models"]) >= 2
        assert len(data["matrix"]) >= 1

    async def test_comparison_matrix_empty(self, client: AsyncClient):
        """Matrix with no battles returns empty matrix."""
        await client.post("/api/models", json={"name": "m1"})
        await client.post("/api/models", json={"name": "m2"})

        resp = await client.get("/api/stats/comparison-matrix")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["models"]) == 2
        assert len(data["matrix"]) == 0

    async def test_comparison_matrix_structure(self, client: AsyncClient):
        """Matrix entry has correct structure."""
        await _setup_battle_with_vote(client)

        resp = await client.get("/api/stats/comparison-matrix")
        data = resp.json()
        entry = data["matrix"][0]
        assert "model_a_id" in entry
        assert "model_a_name" in entry
        assert "model_b_id" in entry
        assert "model_b_name" in entry
        assert "model_a_wins" in entry
        assert "model_b_wins" in entry
        assert "ties" in entry
        assert "total" in entry
        assert "model_a_win_rate" in entry

    async def test_comparison_matrix_multiple_battles(self, client: AsyncClient):
        """Matrix accumulates results across multiple battles."""
        resp_a = await client.post("/api/models", json={"name": "champion"})
        resp_b = await client.post("/api/models", json={"name": "challenger"})
        a_id = resp_a.json()["id"]
        b_id = resp_b.json()["id"]

        # Create 3 battles
        for i in range(3):
            battle_resp = await client.post("/api/arena", json={
                "prompt": f"Q{i}", "response_a": "A", "response_b": "B",
                "model_a_id": a_id, "model_b_id": b_id,
            })
            await client.post("/api/vote", json={
                "battle_id": battle_resp.json()["id"], "winner": "model_a",
            })

        resp = await client.get("/api/stats/comparison-matrix")
        data = resp.json()
        assert len(data["matrix"]) == 1
        assert data["matrix"][0]["total"] == 3


# ── Category Stats ────────────────────────────────────────────────


class TestCategoryStats:
    """Tests for per-category statistics."""

    async def test_category_stats_api(self, client: AsyncClient):
        """Test GET /api/stats/categories."""
        await client.post("/api/models", json={"name": "coder", "category": "coding"})
        await client.post("/api/models", json={"name": "writer", "category": "writing"})

        resp = await client.get("/api/stats/categories")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 2

        categories = {s["category"] for s in data}
        assert "coding" in categories
        assert "writing" in categories

    async def test_category_stats_structure(self, client: AsyncClient):
        """Category stats have correct structure."""
        await client.post("/api/models", json={"name": "test-model", "category": "general"})

        resp = await client.get("/api/stats/categories")
        data = resp.json()
        assert len(data) >= 1
        entry = data[0]
        assert "category" in entry
        assert "model_count" in entry
        assert "avg_rating" in entry
        assert "highest_rating" in entry
        assert "total_battles" in entry
        assert "total_votes" in entry

    async def test_category_stats_empty(self, client: AsyncClient):
        """Category stats returns empty with no models."""
        resp = await client.get("/api/stats/categories")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_category_stats_with_battles(self, client: AsyncClient):
        """Category stats count battles and votes correctly."""
        resp_a = await client.post("/api/models", json={"name": "c1", "category": "coding"})
        resp_b = await client.post("/api/models", json={"name": "c2", "category": "coding"})

        battle_resp = await client.post("/api/arena", json={
            "prompt": "test", "response_a": "A", "response_b": "B",
            "model_a_id": resp_a.json()["id"], "model_b_id": resp_b.json()["id"],
        })
        await client.post("/api/vote", json={"battle_id": battle_resp.json()["id"], "winner": "model_a"})

        resp = await client.get("/api/stats/categories")
        data = resp.json()
        coding = next((s for s in data if s["category"] == "coding"), None)
        assert coding is not None
        assert coding["model_count"] == 2
        assert coding["total_battles"] >= 1
        assert coding["total_votes"] >= 1


# ── Category Stats CLI ────────────────────────────────────────────


class TestCategoryStatsCLI:
    """Tests for the category-stats CLI command."""

    def test_cli_category_stats(self):
        """Test CLI category-stats command."""
        from click.testing import CliRunner
        from evalarena.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["category-stats", "--db", ":memory:"])
        assert result.exit_code == 0


# ── Comparison Matrix CLI ─────────────────────────────────────────


class TestComparisonMatrixCLI:
    """Tests for the comparison-matrix CLI command."""

    def test_cli_comparison_matrix(self):
        """Test CLI comparison-matrix command."""
        from click.testing import CliRunner
        from evalarena.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["comparison-matrix", "--db", ":memory:"])
        assert result.exit_code == 0


# ── Battle Vote Comments DB ───────────────────────────────────────


class TestBattleVoteCommentsDB:
    """Tests for database methods related to vote comments."""

    async def test_get_battle_vote_comments(self, db: Database):
        """Test getting vote comments for a specific battle."""
        model_a = await db.create_model(ModelCreate(name="ma"))
        model_b = await db.create_model(ModelCreate(name="mb"))
        battle = await db.create_battle(BattleCreate(
            prompt="test", response_a="a", response_b="b",
            model_a_id=model_a.id, model_b_id=model_b.id,
        ))
        # Vote with comment
        data = VoteCreate(battle_id=battle.id, winner=Winner.MODEL_A, comment="Better answer")
        await db.create_vote(data)

        comments = await db.get_battle_vote_comments(battle.id)
        assert len(comments) == 1
        assert comments[0]["comment"] == "Better answer"

    async def test_get_battle_vote_no_comments(self, db: Database):
        """Battle with no comments returns empty list."""
        model_a = await db.create_model(ModelCreate(name="ma2"))
        model_b = await db.create_model(ModelCreate(name="mb2"))
        battle = await db.create_battle(BattleCreate(
            prompt="test", response_a="a", response_b="b",
            model_a_id=model_a.id, model_b_id=model_b.id,
        ))
        data = VoteCreate(battle_id=battle.id, winner=Winner.MODEL_A, comment="")
        await db.create_vote(data)

        comments = await db.get_battle_vote_comments(battle.id)
        assert len(comments) == 0

    async def test_get_battles_with_comments_db(self, db: Database):
        """Test getting battles with comments at DB level."""
        model_a = await db.create_model(ModelCreate(name="ma3"))
        model_b = await db.create_model(ModelCreate(name="mb3"))
        battle = await db.create_battle(BattleCreate(
            prompt="test prompt", response_a="a", response_b="b",
            model_a_id=model_a.id, model_b_id=model_b.id,
        ))
        data = VoteCreate(battle_id=battle.id, winner=Winner.MODEL_A, comment="Great response")
        await db.create_vote(data)

        results = await db.get_battles_with_comments()
        assert len(results) >= 1
        found = next((r for r in results if r["id"] == battle.id), None)
        assert found is not None
        assert found["winner_name"] is not None
        assert len(found["comments"]) >= 1
        assert found["comments"][0]["comment"] == "Great response"


# ── Category Stats DB ─────────────────────────────────────────────


class TestCategoryStatsDB:
    """Tests for category stats at the database level."""

    async def test_get_category_stats(self, db: Database):
        """Test get_category_stats method."""
        await db.create_model(ModelCreate(name="db-coder", category="coding"))
        await db.create_model(ModelCreate(name="db-writer", category="writing"))

        stats = await db.get_category_stats()
        categories = {s["category"] for s in stats}
        assert "coding" in categories
        assert "writing" in categories

    async def test_get_category_stats_empty(self, db: Database):
        """Empty database returns empty stats."""
        stats = await db.get_category_stats()
        assert stats == []


# ── Comparison Matrix DB ──────────────────────────────────────────


class TestComparisonMatrixDB:
    """Tests for comparison matrix at the database level."""

    async def test_get_comparison_matrix(self, db: Database):
        """Test get_comparison_matrix method."""
        m_a = await db.create_model(ModelCreate(name="db-champ"))
        m_b = await db.create_model(ModelCreate(name="db-challenger"))

        battle = await db.create_battle(BattleCreate(
            prompt="test", response_a="a", response_b="b",
            model_a_id=m_a.id, model_b_id=m_b.id,
        ))
        await db.create_vote(VoteCreate(battle_id=battle.id, winner=Winner.MODEL_A))

        data = await db.get_comparison_matrix()
        assert len(data["models"]) == 2
        assert len(data["matrix"]) == 1
        assert data["matrix"][0]["total"] == 1

    async def test_get_comparison_matrix_no_battles(self, db: Database):
        """Matrix with models but no battles."""
        await db.create_model(ModelCreate(name="solo1"))
        await db.create_model(ModelCreate(name="solo2"))

        data = await db.get_comparison_matrix()
        assert len(data["models"]) == 2
        assert len(data["matrix"]) == 0
