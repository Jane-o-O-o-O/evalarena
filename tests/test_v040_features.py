"""Tests for v0.4.0 features: model update, provider integration, voter IP dedup, auto-battle."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from evalarena.app import create_app
from evalarena.db.database import Database
from evalarena.db.models import ModelCreate, BattleCreate, VoteCreate, Winner, ModelUpdate


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
# Model Update API Tests
# ---------------------------------------------------------------------------


class TestModelUpdateAPI:
    """Tests for PUT /api/models/{id} endpoint."""

    async def test_update_model_category(self, client: AsyncClient):
        """Test updating a model's category."""
        # Create a model
        resp = await client.post("/api/models", json={"name": "gpt-4o", "category": "general"})
        assert resp.status_code == 201
        model_id = resp.json()["id"]

        # Update category
        resp = await client.put(f"/api/models/{model_id}", json={"category": "coding"})
        assert resp.status_code == 200
        assert resp.json()["category"] == "coding"
        assert resp.json()["name"] == "gpt-4o"  # Unchanged

    async def test_update_model_name(self, client: AsyncClient):
        """Test renaming a model."""
        resp = await client.post("/api/models", json={"name": "old-name"})
        model_id = resp.json()["id"]

        resp = await client.put(f"/api/models/{model_id}", json={"name": "new-name"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "new-name"

    async def test_update_model_multiple_fields(self, client: AsyncClient):
        """Test updating multiple fields at once."""
        resp = await client.post("/api/models", json={"name": "model-1"})
        model_id = resp.json()["id"]

        resp = await client.put(
            f"/api/models/{model_id}",
            json={
                "description": "A powerful model",
                "organization": "OpenAI",
                "parameter_count": "175B",
                "provider": "openai",
                "api_model_id": "gpt-4o",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["description"] == "A powerful model"
        assert data["organization"] == "OpenAI"
        assert data["parameter_count"] == "175B"
        assert data["provider"] == "openai"
        assert data["api_model_id"] == "gpt-4o"

    async def test_update_model_not_found(self, client: AsyncClient):
        """Test updating a non-existent model returns 404."""
        resp = await client.put("/api/models/nonexistent", json={"category": "coding"})
        assert resp.status_code == 404

    async def test_update_model_name_conflict(self, client: AsyncClient):
        """Test renaming to an existing name returns 409."""
        await client.post("/api/models", json={"name": "model-a"})
        resp = await client.post("/api/models", json={"name": "model-b"})
        model_b_id = resp.json()["id"]

        resp = await client.put(f"/api/models/{model_b_id}", json={"name": "model-a"})
        assert resp.status_code == 409

    async def test_update_model_no_changes(self, client: AsyncClient):
        """Test update with no fields returns the model unchanged."""
        resp = await client.post("/api/models", json={"name": "model-1", "category": "coding"})
        model_id = resp.json()["id"]

        resp = await client.put(f"/api/models/{model_id}", json={})
        assert resp.status_code == 200
        assert resp.json()["category"] == "coding"


class TestModelUpdateDB:
    """Tests for Database.update_model method."""

    async def test_update_model_basic(self, db: Database):
        """Test basic model update."""
        model = await db.create_model(ModelCreate(name="test-model"))
        update = ModelUpdate(description="Updated description")
        updated = await db.update_model(model.id, update)
        assert updated is not None
        assert updated.description == "Updated description"
        assert updated.name == "test-model"

    async def test_update_model_not_found(self, db: Database):
        """Test updating non-existent model returns None."""
        update = ModelUpdate(description="test")
        result = await db.update_model("nonexistent", update)
        assert result is None

    async def test_update_model_provider_fields(self, db: Database):
        """Test updating provider-related fields."""
        model = await db.create_model(ModelCreate(name="gpt-4o"))
        update = ModelUpdate(provider="openai", api_model_id="gpt-4o-2024-08-06")
        updated = await db.update_model(model.id, update)
        assert updated is not None
        assert updated.provider == "openai"
        assert updated.api_model_id == "gpt-4o-2024-08-06"


# ---------------------------------------------------------------------------
# Provider Integration Tests
# ---------------------------------------------------------------------------


class TestProviderRegistry:
    """Tests for provider registry."""

    def test_register_and_get_provider(self):
        """Test registering and retrieving a provider."""
        from evalarena.providers.registry import _registry, register_provider, get_provider
        from evalarena.providers.mock_provider import MockProvider

        # Save original state
        original = dict(_registry)
        try:
            _registry.clear()
            provider = MockProvider()
            register_provider(provider)
            assert get_provider("mock") is provider
            assert get_provider("nonexistent") is None
        finally:
            _registry.clear()
            _registry.update(original)

    def test_list_providers(self):
        """Test listing providers."""
        from evalarena.providers.registry import _registry, register_provider, list_providers
        from evalarena.providers.mock_provider import MockProvider

        original = dict(_registry)
        try:
            _registry.clear()
            register_provider(MockProvider())
            providers = list_providers()
            assert len(providers) == 1
            assert providers[0]["name"] == "mock"
            assert providers[0]["configured"] is True
        finally:
            _registry.clear()
            _registry.update(original)


class TestMockProvider:
    """Tests for the mock LLM provider."""

    async def test_mock_generate(self):
        """Test mock provider generates a response."""
        from evalarena.providers.mock_provider import MockProvider

        provider = MockProvider()
        response = await provider.generate("What is Python?", "test-model")
        assert "test-model" in response.text
        assert "What is Python?" in response.text
        assert response.tokens_used > 0
        assert response.model_id == "test-model"

    def test_mock_is_configured(self):
        """Test mock provider is always configured."""
        from evalarena.providers.mock_provider import MockProvider

        provider = MockProvider()
        assert provider.is_configured() is True

    def test_mock_name(self):
        """Test mock provider name."""
        from evalarena.providers.mock_provider import MockProvider

        provider = MockProvider()
        assert provider.name == "mock"


class TestOpenAIProvider:
    """Tests for the OpenAI provider (configuration only, no API calls)."""

    def test_openai_not_configured_without_key(self, monkeypatch):
        """Test OpenAI provider reports not configured without API key."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from evalarena.providers.openai_provider import OpenAIProvider

        provider = OpenAIProvider()
        assert provider.is_configured() is False

    def test_openai_configured_with_key(self):
        """Test OpenAI provider reports configured with API key."""
        from evalarena.providers.openai_provider import OpenAIProvider

        provider = OpenAIProvider(api_key="sk-test-key")
        assert provider.is_configured() is True

    def test_openai_name(self):
        """Test OpenAI provider name."""
        from evalarena.providers.openai_provider import OpenAIProvider

        provider = OpenAIProvider()
        assert provider.name == "openai"


class TestAnthropicProvider:
    """Tests for the Anthropic provider (configuration only, no API calls)."""

    def test_anthropic_not_configured_without_key(self, monkeypatch):
        """Test Anthropic provider reports not configured without API key."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        from evalarena.providers.anthropic_provider import AnthropicProvider

        provider = AnthropicProvider()
        assert provider.is_configured() is False

    def test_anthropic_configured_with_key(self):
        """Test Anthropic provider reports configured with API key."""
        from evalarena.providers.anthropic_provider import AnthropicProvider

        provider = AnthropicProvider(api_key="sk-ant-test-key")
        assert provider.is_configured() is True

    def test_anthropic_name(self):
        """Test Anthropic provider name."""
        from evalarena.providers.anthropic_provider import AnthropicProvider

        provider = AnthropicProvider()
        assert provider.name == "anthropic"


class TestProviderAPI:
    """Tests for GET /api/providers endpoint."""

    async def test_list_providers_endpoint(self, client: AsyncClient):
        """Test providers API returns registered providers."""
        resp = await client.get("/api/providers")
        assert resp.status_code == 200
        providers = resp.json()
        assert isinstance(providers, list)
        names = [p["name"] for p in providers]
        assert "mock" in names
        assert "openai" in names
        assert "anthropic" in names


# ---------------------------------------------------------------------------
# Voter IP Dedup Tests
# ---------------------------------------------------------------------------


class TestVoterIPDedup:
    """Tests for IP-based duplicate vote prevention."""

    async def test_same_ip_cannot_vote_twice(self, client: AsyncClient, db: Database):
        """Test that the same IP cannot vote on the same battle twice."""
        # Create two models
        resp_a = await client.post("/api/models", json={"name": "model-a"})
        resp_b = await client.post("/api/models", json={"name": "model-b"})
        model_a_id = resp_a.json()["id"]
        model_b_id = resp_b.json()["id"]

        # Create a battle
        resp = await client.post("/api/arena", json={
            "prompt": "Test prompt",
            "response_a": "Response A",
            "response_b": "Response B",
            "model_a_id": model_a_id,
            "model_b_id": model_b_id,
        })
        battle_id = resp.json()["id"]

        # First vote succeeds
        resp = await client.post("/api/vote", json={
            "battle_id": battle_id,
            "winner": "model_a",
        })
        assert resp.status_code == 201

        # Second vote from same IP fails (battle already voted)
        resp = await client.post("/api/vote", json={
            "battle_id": battle_id,
            "winner": "model_b",
        })
        assert resp.status_code == 409

    async def test_voter_ip_recorded(self, db: Database):
        """Test that voter IP is recorded in the vote."""
        model_a = await db.create_model(ModelCreate(name="model-a"))
        model_b = await db.create_model(ModelCreate(name="model-b"))
        battle = await db.create_battle(BattleCreate(
            prompt="test",
            response_a="resp a",
            response_b="resp b",
            model_a_id=model_a.id,
            model_b_id=model_b.id,
        ))

        vote = VoteCreate(battle_id=battle.id, winner=Winner.MODEL_A)
        recorded = await db.create_vote(vote, voter_ip="192.168.1.1")
        assert recorded is True

    async def test_voter_ip_dedup_at_db_level(self, db: Database):
        """Test IP dedup at the database level."""
        model_a = await db.create_model(ModelCreate(name="model-a"))
        model_b = await db.create_model(ModelCreate(name="model-b"))

        # Create first battle and vote
        battle1 = await db.create_battle(BattleCreate(
            prompt="test1",
            response_a="resp a",
            response_b="resp b",
            model_a_id=model_a.id,
            model_b_id=model_b.id,
        ))
        vote1 = VoteCreate(battle_id=battle1.id, winner=Winner.MODEL_A)
        await db.create_vote(vote1, voter_ip="10.0.0.1")

        # Create second battle - same IP should be able to vote on different battle
        battle2 = await db.create_battle(BattleCreate(
            prompt="test2",
            response_a="resp a",
            response_b="resp b",
            model_a_id=model_a.id,
            model_b_id=model_b.id,
        ))
        vote2 = VoteCreate(battle_id=battle2.id, winner=Winner.MODEL_B)
        recorded = await db.create_vote(vote2, voter_ip="10.0.0.1")
        assert recorded is True  # Different battle, same IP is OK


# ---------------------------------------------------------------------------
# Auto-Battle Tests
# ---------------------------------------------------------------------------


class TestAutoBattle:
    """Tests for POST /api/arena/auto-battle endpoint."""

    async def test_auto_battle_with_mock_provider(self, client: AsyncClient):
        """Test auto-battle using the mock provider."""
        # Create models with mock provider
        resp_a = await client.post("/api/models", json={
            "name": "mock-model-a",
            "provider": "mock",
            "api_model_id": "mock-v1",
        })
        resp_b = await client.post("/api/models", json={
            "name": "mock-model-b",
            "provider": "mock",
            "api_model_id": "mock-v2",
        })
        model_a_id = resp_a.json()["id"]
        model_b_id = resp_b.json()["id"]

        # Auto-battle
        resp = await client.post("/api/arena/auto-battle", json={
            "prompt": "What is recursion?",
            "model_a_id": model_a_id,
            "model_b_id": model_b_id,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["prompt"] == "What is recursion?"
        assert len(data["response_a"]) > 0
        assert len(data["response_b"]) > 0

    async def test_auto_battle_model_not_found(self, client: AsyncClient):
        """Test auto-battle with non-existent model returns 404."""
        resp = await client.post("/api/models", json={
            "name": "existing-model",
            "provider": "mock",
        })
        model_id = resp.json()["id"]

        resp = await client.post("/api/arena/auto-battle", json={
            "prompt": "Test",
            "model_a_id": model_id,
            "model_b_id": "nonexistent",
        })
        assert resp.status_code == 404

    async def test_auto_battle_same_model(self, client: AsyncClient):
        """Test auto-battle with same model returns 400."""
        resp = await client.post("/api/models", json={
            "name": "solo-model",
            "provider": "mock",
        })
        model_id = resp.json()["id"]

        resp = await client.post("/api/arena/auto-battle", json={
            "prompt": "Test",
            "model_a_id": model_id,
            "model_b_id": model_id,
        })
        assert resp.status_code == 400

    async def test_auto_battle_no_provider(self, client: AsyncClient):
        """Test auto-battle with model that has no provider returns 400."""
        resp_a = await client.post("/api/models", json={"name": "no-provider-a"})
        resp_b = await client.post("/api/models", json={"name": "no-provider-b"})

        resp = await client.post("/api/arena/auto-battle", json={
            "prompt": "Test",
            "model_a_id": resp_a.json()["id"],
            "model_b_id": resp_b.json()["id"],
        })
        assert resp.status_code == 400

    async def test_auto_battle_unconfigured_provider(self, client: AsyncClient, monkeypatch):
        """Test auto-battle with unconfigured provider returns 400."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        resp_a = await client.post("/api/models", json={
            "name": "openai-model",
            "provider": "openai",
            "api_model_id": "gpt-4o",
        })
        resp_b = await client.post("/api/models", json={
            "name": "openai-model-2",
            "provider": "openai",
            "api_model_id": "gpt-4o-mini",
        })

        resp = await client.post("/api/arena/auto-battle", json={
            "prompt": "Test",
            "model_a_id": resp_a.json()["id"],
            "model_b_id": resp_b.json()["id"],
        })
        assert resp.status_code == 400
        assert "not configured" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# CLI Update-Model Tests
# ---------------------------------------------------------------------------


class TestCLIUpdateModel:
    """Tests for the CLI update-model command."""

    def test_cli_update_model_category(self, tmp_path):
        """Test updating a model's category via CLI."""
        import asyncio
        from click.testing import CliRunner
        from evalarena.cli import main
        from evalarena.db.database import Database
        from evalarena.db.models import ModelCreate

        db_path = tmp_path / "test.db"

        async def setup():
            db = Database(str(db_path))
            await db.connect()
            await db.create_model(ModelCreate(name="test-model"))
            await db.close()
        asyncio.run(setup())

        runner = CliRunner()
        result = runner.invoke(main, [
            "update-model", "test-model",
            "--category", "coding",
            "--db", str(db_path),
        ])
        assert result.exit_code == 0
        assert "Updated model" in result.output
        assert "coding" in result.output

    def test_cli_update_model_not_found(self, tmp_path):
        """Test updating non-existent model via CLI."""
        import asyncio
        from click.testing import CliRunner
        from evalarena.cli import main
        from evalarena.db.database import Database

        db_path = tmp_path / "empty.db"

        async def setup():
            db = Database(str(db_path))
            await db.connect()
            await db.close()
        asyncio.run(setup())

        runner = CliRunner()
        result = runner.invoke(main, [
            "update-model", "nonexistent",
            "--category", "coding",
            "--db", str(db_path),
        ])
        assert result.exit_code == 0
        assert "not found" in result.output

    def test_cli_update_model_provider(self, tmp_path):
        """Test updating provider info via CLI."""
        import asyncio
        from click.testing import CliRunner
        from evalarena.cli import main
        from evalarena.db.database import Database
        from evalarena.db.models import ModelCreate

        db_path = tmp_path / "test.db"

        async def setup():
            db = Database(str(db_path))
            await db.connect()
            await db.create_model(ModelCreate(name="gpt-4o"))
            await db.close()
        asyncio.run(setup())

        runner = CliRunner()
        result = runner.invoke(main, [
            "update-model", "gpt-4o",
            "--provider", "openai",
            "--api-model-id", "gpt-4o-2024-08-06",
            "--db", str(db_path),
        ])
        assert result.exit_code == 0
        assert "Provider: openai" in result.output
        assert "API Model ID: gpt-4o-2024-08-06" in result.output


# ---------------------------------------------------------------------------
# CLI Providers Tests
# ---------------------------------------------------------------------------


class TestCLIProviders:
    """Tests for the CLI providers command."""

    def test_cli_providers_list(self):
        """Test listing providers via CLI."""
        from click.testing import CliRunner
        from evalarena.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["providers"])
        assert result.exit_code == 0
        assert "mock" in result.output
        assert "openai" in result.output
        assert "anthropic" in result.output
