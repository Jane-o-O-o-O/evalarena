"""Tests for v0.5.0 features: prompt templates, vote comments, batch battles,
model trends, battle export, template CLI commands."""

from __future__ import annotations

import json
import pytest
from httpx import ASGITransport, AsyncClient

from evalarena.app import create_app
from evalarena.db.database import Database
from evalarena.db.models import (
    ModelCreate,
    BattleCreate,
    VoteCreate,
    Winner,
    PromptTemplateCreate,
    PromptTemplateUpdate,
)


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


# ---------------------------------------------------------------------------
# Prompt Template DB Tests
# ---------------------------------------------------------------------------


class TestPromptTemplateDB:
    """Tests for prompt template database operations."""

    async def test_create_template(self, db: Database):
        """Test creating a prompt template."""
        data = PromptTemplateCreate(
            name="Explain recursion",
            prompt_text="Explain recursion in simple terms with an example.",
            category="coding",
            description="Tests explanation of basic CS concepts",
        )
        template = await db.create_prompt_template(data)
        assert template.name == "Explain recursion"
        assert template.prompt_text == "Explain recursion in simple terms with an example."
        assert template.category == "coding"
        assert template.description == "Tests explanation of basic CS concepts"
        assert template.usage_count == 0
        assert template.id

    async def test_get_template_by_id(self, db: Database):
        """Test retrieving a template by ID."""
        data = PromptTemplateCreate(name="Test", prompt_text="Hello world", category="general")
        created = await db.create_prompt_template(data)
        found = await db.get_prompt_template(created.id)
        assert found is not None
        assert found.name == "Test"

    async def test_get_template_not_found(self, db: Database):
        """Test that non-existent template returns None."""
        found = await db.get_prompt_template("nonexistent")
        assert found is None

    async def test_get_template_by_name(self, db: Database):
        """Test retrieving a template by name."""
        data = PromptTemplateCreate(name="Unique Name", prompt_text="Some prompt", category="general")
        await db.create_prompt_template(data)
        found = await db.get_prompt_template_by_name("Unique Name")
        assert found is not None
        assert found.name == "Unique Name"

    async def test_list_templates(self, db: Database):
        """Test listing all templates."""
        await db.create_prompt_template(PromptTemplateCreate(name="T1", prompt_text="P1", category="coding"))
        await db.create_prompt_template(PromptTemplateCreate(name="T2", prompt_text="P2", category="writing"))
        await db.create_prompt_template(PromptTemplateCreate(name="T3", prompt_text="P3", category="coding"))
        templates = await db.list_prompt_templates()
        assert len(templates) == 3

    async def test_list_templates_by_category(self, db: Database):
        """Test listing templates filtered by category."""
        await db.create_prompt_template(PromptTemplateCreate(name="T1", prompt_text="P1", category="coding"))
        await db.create_prompt_template(PromptTemplateCreate(name="T2", prompt_text="P2", category="writing"))
        templates = await db.list_prompt_templates(category="coding")
        assert len(templates) == 1
        assert templates[0].category == "coding"

    async def test_update_template(self, db: Database):
        """Test updating a template's fields."""
        data = PromptTemplateCreate(name="Old Name", prompt_text="Old prompt", category="general")
        created = await db.create_prompt_template(data)
        update = PromptTemplateUpdate(name="New Name", category="coding")
        updated = await db.update_prompt_template(created.id, update)
        assert updated is not None
        assert updated.name == "New Name"
        assert updated.category == "coding"
        assert updated.prompt_text == "Old prompt"  # Unchanged

    async def test_update_template_not_found(self, db: Database):
        """Test updating a non-existent template returns None."""
        update = PromptTemplateUpdate(name="New")
        result = await db.update_prompt_template("nonexistent", update)
        assert result is None

    async def test_delete_template(self, db: Database):
        """Test deleting a template."""
        data = PromptTemplateCreate(name="To Delete", prompt_text="...", category="general")
        created = await db.create_prompt_template(data)
        deleted = await db.delete_prompt_template(created.id)
        assert deleted is True
        assert await db.get_prompt_template(created.id) is None

    async def test_delete_template_not_found(self, db: Database):
        """Test deleting a non-existent template returns False."""
        deleted = await db.delete_prompt_template("nonexistent")
        assert deleted is False

    async def test_increment_usage(self, db: Database):
        """Test incrementing template usage counter."""
        data = PromptTemplateCreate(name="Counter", prompt_text="...", category="general")
        created = await db.create_prompt_template(data)
        assert created.usage_count == 0
        await db.increment_template_usage(created.id)
        await db.increment_template_usage(created.id)
        found = await db.get_prompt_template(created.id)
        assert found is not None
        assert found.usage_count == 2

    async def test_list_template_categories(self, db: Database):
        """Test listing template categories."""
        await db.create_prompt_template(PromptTemplateCreate(name="T1", prompt_text="P1", category="coding"))
        await db.create_prompt_template(PromptTemplateCreate(name="T2", prompt_text="P2", category="writing"))
        await db.create_prompt_template(PromptTemplateCreate(name="T3", prompt_text="P3", category="coding"))
        categories = await db.list_template_categories()
        assert categories == ["coding", "writing"]


# ---------------------------------------------------------------------------
# Prompt Template API Tests
# ---------------------------------------------------------------------------


class TestPromptTemplateAPI:
    """Tests for prompt template API endpoints."""

    async def test_create_template(self, client: AsyncClient):
        """Test POST /api/templates."""
        resp = await client.post("/api/templates", json={
            "name": "Test Template",
            "prompt_text": "Explain recursion.",
            "category": "coding",
            "description": "A test template",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Template"
        assert data["category"] == "coding"
        assert data["usage_count"] == 0

    async def test_create_duplicate_template(self, client: AsyncClient):
        """Test creating a template with duplicate name returns 409."""
        await client.post("/api/templates", json={
            "name": "Duplicate", "prompt_text": "Hello", "category": "general"
        })
        resp = await client.post("/api/templates", json={
            "name": "Duplicate", "prompt_text": "World", "category": "general"
        })
        assert resp.status_code == 409

    async def test_list_templates(self, client: AsyncClient):
        """Test GET /api/templates."""
        await client.post("/api/templates", json={
            "name": "T1", "prompt_text": "P1", "category": "coding"
        })
        await client.post("/api/templates", json={
            "name": "T2", "prompt_text": "P2", "category": "writing"
        })
        resp = await client.get("/api/templates")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_list_templates_by_category(self, client: AsyncClient):
        """Test GET /api/templates?category=coding."""
        await client.post("/api/templates", json={
            "name": "T1", "prompt_text": "P1", "category": "coding"
        })
        await client.post("/api/templates", json={
            "name": "T2", "prompt_text": "P2", "category": "writing"
        })
        resp = await client.get("/api/templates?category=coding")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_get_template(self, client: AsyncClient):
        """Test GET /api/templates/{id}."""
        create_resp = await client.post("/api/templates", json={
            "name": "Fetch Me", "prompt_text": "Hello", "category": "general"
        })
        template_id = create_resp.json()["id"]
        resp = await client.get(f"/api/templates/{template_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Fetch Me"

    async def test_get_template_not_found(self, client: AsyncClient):
        """Test GET /api/templates/{id} with non-existent ID."""
        resp = await client.get("/api/templates/nonexistent")
        assert resp.status_code == 404

    async def test_update_template(self, client: AsyncClient):
        """Test PUT /api/templates/{id}."""
        create_resp = await client.post("/api/templates", json={
            "name": "To Update", "prompt_text": "Old", "category": "general"
        })
        template_id = create_resp.json()["id"]
        resp = await client.put(f"/api/templates/{template_id}", json={
            "name": "Updated", "category": "coding"
        })
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated"
        assert resp.json()["category"] == "coding"

    async def test_update_template_name_conflict(self, client: AsyncClient):
        """Test updating a template to a name that already exists."""
        await client.post("/api/templates", json={
            "name": "Existing", "prompt_text": "P1", "category": "general"
        })
        create_resp = await client.post("/api/templates", json={
            "name": "Other", "prompt_text": "P2", "category": "general"
        })
        template_id = create_resp.json()["id"]
        resp = await client.put(f"/api/templates/{template_id}", json={"name": "Existing"})
        assert resp.status_code == 409

    async def test_delete_template(self, client: AsyncClient):
        """Test DELETE /api/templates/{id}."""
        create_resp = await client.post("/api/templates", json={
            "name": "To Delete", "prompt_text": "Hello", "category": "general"
        })
        template_id = create_resp.json()["id"]
        resp = await client.delete(f"/api/templates/{template_id}")
        assert resp.status_code == 204
        # Verify deleted
        resp = await client.get(f"/api/templates/{template_id}")
        assert resp.status_code == 404

    async def test_delete_template_not_found(self, client: AsyncClient):
        """Test DELETE /api/templates/{id} with non-existent ID."""
        resp = await client.delete("/api/templates/nonexistent")
        assert resp.status_code == 404

    async def test_list_template_categories(self, client: AsyncClient):
        """Test GET /api/templates/categories."""
        await client.post("/api/templates", json={
            "name": "T1", "prompt_text": "P1", "category": "coding"
        })
        await client.post("/api/templates", json={
            "name": "T2", "prompt_text": "P2", "category": "writing"
        })
        resp = await client.get("/api/templates/categories")
        assert resp.status_code == 200
        assert resp.json() == ["coding", "writing"]


# ---------------------------------------------------------------------------
# Vote Comment Tests
# ---------------------------------------------------------------------------


class TestVoteComments:
    """Tests for vote comments feature."""

    async def _create_battle(self, client: AsyncClient) -> str:
        """Helper: create a model and battle for voting tests."""
        resp_a = await client.post("/api/models", json={"name": "model-a"})
        resp_b = await client.post("/api/models", json={"name": "model-b"})
        model_a_id = resp_a.json()["id"]
        model_b_id = resp_b.json()["id"]
        battle_resp = await client.post("/api/arena", json={
            "prompt": "Hello",
            "response_a": "Response A",
            "response_b": "Response B",
            "model_a_id": model_a_id,
            "model_b_id": model_b_id,
        })
        return battle_resp.json()["id"]

    async def test_vote_with_comment(self, client: AsyncClient):
        """Test voting with an optional comment."""
        battle_id = await self._create_battle(client)
        resp = await client.post("/api/vote", json={
            "battle_id": battle_id,
            "winner": "model_a",
            "comment": "Response A was more detailed and accurate.",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["winner"] == "model_a"
        assert data["comment"] == "Response A was more detailed and accurate."

    async def test_vote_without_comment(self, client: AsyncClient):
        """Test voting without a comment (default empty string)."""
        battle_id = await self._create_battle(client)
        resp = await client.post("/api/vote", json={
            "battle_id": battle_id,
            "winner": "model_b",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["comment"] == ""

    async def test_vote_with_empty_comment(self, client: AsyncClient):
        """Test voting with an explicitly empty comment."""
        battle_id = await self._create_battle(client)
        resp = await client.post("/api/vote", json={
            "battle_id": battle_id,
            "winner": "tie",
            "comment": "",
        })
        assert resp.status_code == 201
        assert resp.json()["comment"] == ""


# ---------------------------------------------------------------------------
# Model Trends API Tests
# ---------------------------------------------------------------------------


class TestModelTrendsAPI:
    """Tests for model trends endpoint."""

    async def test_get_model_trends(self, client: AsyncClient, db: Database):
        """Test GET /api/models/{id}/trends."""
        # Create models
        resp_a = await client.post("/api/models", json={"name": "model-a"})
        resp_b = await client.post("/api/models", json={"name": "model-b"})
        model_a_id = resp_a.json()["id"]
        model_b_id = resp_b.json()["id"]

        # Create and vote on a battle
        battle_resp = await client.post("/api/arena", json={
            "prompt": "Hello", "response_a": "A", "response_b": "B",
            "model_a_id": model_a_id, "model_b_id": model_b_id,
        })
        battle_id = battle_resp.json()["id"]
        await client.post("/api/vote", json={"battle_id": battle_id, "winner": "model_a"})

        # Get trends
        resp = await client.get(f"/api/models/{model_a_id}/trends")
        assert resp.status_code == 200
        data = resp.json()
        assert data["model_id"] == model_a_id
        assert data["model_name"] == "model-a"
        # Rating change sign depends on random A/B swap in battle creation
        assert len(data["points"]) == 1
        point = data["points"][0]
        # The vote was "model_a" winner — model_a_id could be battle model_a OR model_b
        # depending on random swap. Just verify trend data is well-formed.
        assert point["result"] in ("win", "loss")
        assert point["rating_change"] != 0  # Should have changed from initial 1000
        assert data["current_rating"] != 1000  # Changed from initial

    async def test_get_model_trends_not_found(self, client: AsyncClient):
        """Test trends for non-existent model returns 404."""
        resp = await client.get("/api/models/nonexistent/trends")
        assert resp.status_code == 404

    async def test_get_model_trends_empty(self, client: AsyncClient):
        """Test trends for model with no battles."""
        resp_a = await client.post("/api/models", json={"name": "model-a"})
        model_a_id = resp_a.json()["id"]
        resp = await client.get(f"/api/models/{model_a_id}/trends")
        assert resp.status_code == 200
        assert resp.json()["points"] == []


# ---------------------------------------------------------------------------
# Battle Export Tests
# ---------------------------------------------------------------------------


class TestBattleExportDB:
    """Tests for battle export database operations."""

    async def test_export_battles(self, db: Database):
        """Test exporting battles with vote details."""
        # Create models
        model_a = await db.create_model(ModelCreate(name="model-a"))
        model_b = await db.create_model(ModelCreate(name="model-b"))

        # Create battle
        battle = await db.create_battle(BattleCreate(
            prompt="Test prompt",
            response_a="Response A",
            response_b="Response B",
            model_a_id=model_a.id,
            model_b_id=model_b.id,
        ))

        # Vote with comment
        await db.create_vote(
            VoteCreate(battle_id=battle.id, winner=Winner.MODEL_A, comment="A was better"),
            voter_ip="127.0.0.1",
        )

        # Export
        exported = await db.export_battles()
        assert len(exported) == 1
        assert exported[0]["model_a_name"] == "model-a"
        assert exported[0]["model_b_name"] == "model-b"
        assert exported[0]["winner"] == "model_a"
        assert exported[0]["vote_comment"] == "A was better"

    async def test_export_empty(self, db: Database):
        """Test exporting when no battles exist."""
        exported = await db.export_battles()
        assert exported == []


# ---------------------------------------------------------------------------
# Template Random Battle API Tests
# ---------------------------------------------------------------------------


class TestTemplateRandomBattle:
    """Tests for template-based random battle endpoint."""

    async def test_random_battle_from_template(self, client: AsyncClient):
        """Test GET /api/templates/{id}/random-battle."""
        # Create models
        await client.post("/api/models", json={"name": "model-a"})
        await client.post("/api/models", json={"name": "model-b"})

        # Create template
        template_resp = await client.post("/api/templates", json={
            "name": "Test", "prompt_text": "Hello world", "category": "general"
        })
        template_id = template_resp.json()["id"]

        # Get random battle
        resp = await client.get(f"/api/templates/{template_id}/random-battle")
        assert resp.status_code == 200
        data = resp.json()
        assert data["template_id"] == template_id
        assert data["prompt"] == "Hello world"
        assert data["model_a"] != data["model_b"]
        assert data["model_a_name"]
        assert data["model_b_name"]

        # Verify usage count incremented
        template = await client.get(f"/api/templates/{template_id}")
        assert template.json()["usage_count"] == 1

    async def test_random_battle_template_not_found(self, client: AsyncClient):
        """Test random battle with non-existent template."""
        resp = await client.get("/api/templates/nonexistent/random-battle")
        assert resp.status_code == 404

    async def test_random_battle_insufficient_models(self, client: AsyncClient):
        """Test random battle with less than 2 models."""
        await client.post("/api/models", json={"name": "model-a"})
        template_resp = await client.post("/api/templates", json={
            "name": "Test", "prompt_text": "Hello", "category": "general"
        })
        template_id = template_resp.json()["id"]
        resp = await client.get(f"/api/templates/{template_id}/random-battle")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Version Check
# ---------------------------------------------------------------------------


class TestVersion:
    """Test version was bumped to 0.7.0."""

    async def test_health_version(self, client: AsyncClient):
        """Test health endpoint shows v0.7.0."""
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["version"] == "0.7.0"

    async def test_version_in_module(self):
        """Test __version__ is 0.7.0."""
        from evalarena import __version__
        assert __version__ == "0.7.0"


# ---------------------------------------------------------------------------
# CLI Template Commands Tests
# ---------------------------------------------------------------------------


class TestCLITemplateCommands:
    """Tests for CLI prompt template commands."""

    def test_cli_add_template(self):
        """Test CLI add-template command."""
        from click.testing import CliRunner
        from evalarena.cli import main

        runner = CliRunner()
        result = runner.invoke(main, [
            "add-template", "Test CLI Template",
            "--prompt", "Explain recursion.",
            "--category", "coding",
            "--description", "A CLI test template",
            "--db", ":memory:",
        ])
        assert result.exit_code == 0
        assert "Added template" in result.output

    def test_cli_list_templates(self):
        """Test CLI list-templates command."""
        from click.testing import CliRunner
        from evalarena.cli import main

        runner = CliRunner()
        # First add a template
        runner.invoke(main, [
            "add-template", "CLI List Test",
            "--prompt", "Hello world",
            "--db", ":memory:",
        ])
        # List
        result = runner.invoke(main, ["list-templates", "--db", ":memory:"])
        assert result.exit_code == 0

    def test_cli_delete_template(self, tmp_path):
        """Test CLI delete-template command."""
        from click.testing import CliRunner
        from evalarena.cli import main

        db_path = str(tmp_path / "test.db")
        runner = CliRunner()
        # Add template
        runner.invoke(main, [
            "add-template", "Delete Me",
            "--prompt", "To be deleted",
            "--db", db_path,
        ])
        # Delete
        result = runner.invoke(main, [
            "delete-template", "Delete Me", "--yes", "--db", db_path,
        ])
        assert result.exit_code == 0
        assert "Deleted template" in result.output

    def test_cli_delete_template_not_found(self):
        """Test CLI delete-template with non-existent template."""
        from click.testing import CliRunner
        from evalarena.cli import main

        runner = CliRunner()
        result = runner.invoke(main, [
            "delete-template", "Nonexistent", "--yes", "--db", ":memory:",
        ])
        assert result.exit_code == 0
        assert "not found" in result.output


# ---------------------------------------------------------------------------
# CLI Export Battles Tests
# ---------------------------------------------------------------------------


class TestCLIExportBattles:
    """Tests for CLI battle export command."""

    def test_cli_export_battles_json(self, tmp_path):
        """Test CLI export-battles to JSON."""
        import asyncio
        from click.testing import CliRunner
        from evalarena.cli import main

        db_path = str(tmp_path / "test.db")
        output_path = str(tmp_path / "export.json")

        # Setup: create model, battle, vote
        async def _setup():
            db = Database(db_path)
            await db.connect()
            model_a = await db.create_model(ModelCreate(name="model-a"))
            model_b = await db.create_model(ModelCreate(name="model-b"))
            battle = await db.create_battle(BattleCreate(
                prompt="Test", response_a="A", response_b="B",
                model_a_id=model_a.id, model_b_id=model_b.id,
            ))
            await db.create_vote(
                VoteCreate(battle_id=battle.id, winner=Winner.MODEL_A, comment="A is better"),
                voter_ip="127.0.0.1",
            )
            await db.close()

        asyncio.run(_setup())

        runner = CliRunner()
        result = runner.invoke(main, [
            "export-battles", "--output", output_path, "--db", db_path,
        ])
        assert result.exit_code == 0
        assert "Exported" in result.output

        # Verify file
        with open(output_path) as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["vote_comment"] == "A is better"
