"""Tests for model registration and management."""
import pytest

from evalarena.core.models import (
    register_model,
    get_model,
    get_model_by_name,
    list_models,
    update_model_rating,
    delete_model,
    ModelInfo,
)


class TestModelRegistration:
    """Tests for registering models."""

    async def test_register_model(self, db):
        """Should register a model and return ModelInfo."""
        model = await register_model("gpt-4o", "OpenAI", "GPT-4 Omni")
        assert model.name == "gpt-4o"
        assert model.organization == "OpenAI"
        assert model.description == "GPT-4 Omni"
        assert model.elo_rating == 1000.0
        assert model.games_played == 0
        assert model.id is not None

    async def test_register_model_defaults(self, db):
        """Should register with default ELO when not specified."""
        model = await register_model("claude-3")
        assert model.elo_rating == 1000.0
        assert model.organization is None

    async def test_register_model_custom_elo(self, db):
        """Should register with custom initial ELO."""
        model = await register_model("custom-model", initial_elo=1200.0)
        assert model.elo_rating == 1200.0

    async def test_register_duplicate_name_fails(self, db):
        """Should not allow duplicate model names."""
        await register_model("gpt-4o")
        with pytest.raises(Exception):
            await register_model("gpt-4o")


class TestModelRetrieval:
    """Tests for getting models."""

    async def test_get_model_by_id(self, db):
        """Should get a model by its ID."""
        created = await register_model("model-a")
        fetched = await get_model(created.id)
        assert fetched is not None
        assert fetched.name == "model-a"

    async def test_get_nonexistent_model(self, db):
        """Should return None for non-existent model."""
        result = await get_model(999)
        assert result is None

    async def test_get_model_by_name(self, db):
        """Should get a model by name."""
        await register_model("gpt-4o", "OpenAI")
        model = await get_model_by_name("gpt-4o")
        assert model is not None
        assert model.organization == "OpenAI"

    async def test_get_model_by_name_not_found(self, db):
        """Should return None for non-existent name."""
        result = await get_model_by_name("nonexistent")
        assert result is None


class TestModelListing:
    """Tests for listing models."""

    async def test_list_models_empty(self, db):
        """Should return empty list when no models."""
        models = await list_models()
        assert models == []

    async def test_list_models_ordered_by_elo(self, db):
        """Should list models ordered by ELO rating descending."""
        await register_model("low-elo", initial_elo=900.0)
        await register_model("high-elo", initial_elo=1200.0)
        await register_model("mid-elo", initial_elo=1000.0)

        models = await list_models()
        assert len(models) == 3
        assert models[0].name == "high-elo"
        assert models[1].name == "mid-elo"
        assert models[2].name == "low-elo"

    async def test_list_models_ordered_by_name(self, db):
        """Should list models ordered by name ascending."""
        await register_model("beta")
        await register_model("alpha")
        await register_model("gamma")

        models = await list_models(order_by="name", descending=False)
        assert models[0].name == "alpha"
        assert models[1].name == "beta"
        assert models[2].name == "gamma"


class TestModelRatingUpdate:
    """Tests for updating model ratings."""

    async def test_update_rating_win(self, db):
        """Should update rating and stats on a win."""
        model = await register_model("winner")
        await update_model_rating(model.id, 1016.0, won=True)

        updated = await get_model(model.id)
        assert updated.elo_rating == 1016.0
        assert updated.games_played == 1
        assert updated.wins == 1
        assert updated.losses == 0

    async def test_update_rating_loss(self, db):
        """Should update rating and stats on a loss."""
        model = await register_model("loser")
        await update_model_rating(model.id, 984.0, lost=True)

        updated = await get_model(model.id)
        assert updated.elo_rating == 984.0
        assert updated.games_played == 1
        assert updated.losses == 1
        assert updated.wins == 0

    async def test_update_rating_tie(self, db):
        """Should update stats on a tie."""
        model = await register_model("tie-model")
        await update_model_rating(model.id, 1000.0, tied=True)

        updated = await get_model(model.id)
        assert updated.games_played == 1
        assert updated.ties == 1

    async def test_multiple_games(self, db):
        """Should track cumulative stats."""
        model = await register_model("veteran")
        await update_model_rating(model.id, 1016.0, won=True)
        await update_model_rating(model.id, 1032.0, won=True)
        await update_model_rating(model.id, 1016.0, lost=True)

        updated = await get_model(model.id)
        assert updated.games_played == 3
        assert updated.wins == 2
        assert updated.losses == 1


class TestModelDeletion:
    """Tests for deleting models."""

    async def test_delete_model(self, db):
        """Should delete a model."""
        model = await register_model("doomed")
        result = await delete_model(model.id)
        assert result is True
        assert await get_model(model.id) is None

    async def test_delete_nonexistent(self, db):
        """Should return False when deleting non-existent model."""
        result = await delete_model(999)
        assert result is False


class TestModelInfo:
    """Tests for ModelInfo dataclass."""

    def test_win_rate_no_games(self):
        """Should return 0% when no games played."""
        m = ModelInfo(id=1, name="test")
        assert m.win_rate == 0.0

    def test_win_rate_calculation(self):
        """Should calculate correct win rate."""
        m = ModelInfo(id=1, name="test", games_played=10, wins=7)
        assert m.win_rate == 70.0

    def test_to_dict(self):
        """Should serialize to dictionary."""
        m = ModelInfo(id=1, name="test", organization="org")
        d = m.to_dict()
        assert d["id"] == 1
        assert d["name"] == "test"
        assert d["win_rate"] == 0.0
        assert "elo_rating" in d
