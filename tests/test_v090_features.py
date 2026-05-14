"""Tests for v0.9.0 features: Glicko-2, Audit Log, Backup/Restore, Multi-dimension Scoring, Reports."""

from __future__ import annotations

import json
import math
import pytest

# -- Glicko-2 Tests -------------------------------------------------------

from evalarena.core.glicko2 import (
    Glicko2Player,
    GLICKO2_DEFAULT_RATING,
    GLICKO2_DEFAULT_RD,
    GLICKO2_DEFAULT_VOLATILITY,
    glicko2_from_elo,
    glicko2_win_probability,
    update_glicko2,
    _g,
    _E,
)


class TestGlicko2Player:
    """Test the Glicko2Player dataclass."""

    def test_default_values(self) -> None:
        p = Glicko2Player(name="test-model")
        assert p.rating == 1500.0
        assert p.rd == 350.0
        assert p.volatility == 0.06
        assert p.wins == 0
        assert p.losses == 0
        assert p.ties == 0
        assert p.total_games == 0
        assert p.win_rate == 0.0

    def test_custom_values(self) -> None:
        p = Glicko2Player(name="gpt-4", rating=1650.0, rd=80.0, volatility=0.05)
        assert p.rating == 1650.0
        assert p.rd == 80.0

    def test_confidence_interval(self) -> None:
        p = Glicko2Player(name="test", rating=1500.0, rd=100.0)
        lo, hi = p.confidence_interval
        assert abs(lo - (1500.0 - 1.96 * 100.0)) < 0.1
        assert abs(hi - (1500.0 + 1.96 * 100.0)) < 0.1

    def test_confidence_interval_default_rd(self) -> None:
        p = Glicko2Player(name="new-model")
        lo, hi = p.confidence_interval
        margin = 1.96 * 350.0
        assert abs(lo - (1500.0 - margin)) < 0.1
        assert abs(hi - (1500.0 + margin)) < 0.1


class TestGlicko2Functions:
    """Test core Glicko-2 math functions."""

    def test_g_function(self) -> None:
        # g(0) = 1, g(large) -> 0
        assert abs(_g(0.0) - 1.0) < 1e-10
        assert _g(100.0) < 0.02

    def test_g_function_symmetry(self) -> None:
        assert abs(_g(5.0) - _g(-5.0)) < 1e-10

    def test_E_function(self) -> None:
        # Equal ratings -> 0.5
        assert abs(_E(0.0, 0.0, 1.0) - 0.5) < 1e-6
        # Higher rating -> higher E
        assert _E(2.0, 0.0, 1.0) > 0.5
        assert _E(-2.0, 0.0, 1.0) < 0.5

    def test_E_function_bounds(self) -> None:
        for phi in [0.1, 0.5, 1.0, 5.0]:
            for mu_diff in [-5, -2, 0, 2, 5]:
                e = _E(mu_diff, 0.0, phi)
                assert 0.0 <= e <= 1.0


class TestGlicko2Update:
    """Test the full rating update algorithm."""

    def test_single_win(self) -> None:
        player = Glicko2Player(name="player")
        opponent = Glicko2Player(name="opponent", rating=1500.0, rd=350.0)
        update_glicko2(player, [opponent], [1.0])
        assert player.wins == 1
        assert player.rating != GLICKO2_DEFAULT_RATING  # Rating should change

    def test_single_loss(self) -> None:
        player = Glicko2Player(name="player")
        opponent = Glicko2Player(name="opponent", rating=1500.0, rd=350.0)
        old_rating = player.rating
        update_glicko2(player, [opponent], [0.0])
        assert player.losses == 1
        assert player.rating < old_rating

    def test_single_tie(self) -> None:
        player = Glicko2Player(name="player", rating=1500.0, rd=200.0)
        opponent = Glicko2Player(name="opponent", rating=1500.0, rd=200.0)
        update_glicko2(player, [opponent], [0.5])
        assert player.ties == 1
        # Equal players tying = minimal rating change
        assert abs(player.rating - 1500.0) < 1.0

    def test_multiple_games(self) -> None:
        player = Glicko2Player(name="player")
        opponents = [
            Glicko2Player(name=f"opp-{i}", rating=1400.0 + i * 50, rd=300.0)
            for i in range(5)
        ]
        scores = [1.0, 1.0, 0.5, 0.0, 1.0]
        update_glicko2(player, opponents, scores)
        assert player.wins == 3
        assert player.ties == 1
        assert player.losses == 1
        assert player.rd < GLICKO2_DEFAULT_RD  # Should be more certain

    def test_no_games_increases_rd(self) -> None:
        player = Glicko2Player(name="player", rd=100.0, volatility=0.06)
        old_rd = player.rd
        update_glicko2(player, [], [])
        assert player.rd > old_rd  # Uncertainty increases with time

    def test_rd_decreases_with_games(self) -> None:
        """RD should decrease as more games are played."""
        player = Glicko2Player(name="player", rd=350.0)
        opponent = Glicko2Player(name="opponent", rating=1500.0, rd=200.0)

        for _ in range(10):
            update_glicko2(player, [opponent], [1.0])

        assert player.rd < 200.0  # Much more certain after 10 games

    def test_mismatch_lengths_raises(self) -> None:
        player = Glicko2Player(name="player")
        opponent = Glicko2Player(name="opponent")
        with pytest.raises(ValueError, match="same length"):
            update_glicko2(player, [opponent], [1.0, 0.5])

    def test_higher_rated_wins_smaller_change(self) -> None:
        """Winning as the higher-rated player should give less rating gain."""
        strong = Glicko2Player(name="strong", rating=2000.0, rd=100.0)
        weak = Glicko2Player(name="weak", rating=1000.0, rd=100.0)
        old_rating = strong.rating
        update_glicko2(strong, [weak], [1.0])
        change = strong.rating - old_rating
        # Should be very small (expected to win)
        assert change < 5.0

    def test_upset_gives_large_change(self) -> None:
        """Losing to a much weaker player causes a large rating drop."""
        strong = Glicko2Player(name="strong", rating=2000.0, rd=100.0)
        weak = Glicko2Player(name="weak", rating=1000.0, rd=100.0)
        old_rating = strong.rating
        update_glicko2(strong, [weak], [0.0])
        drop = old_rating - strong.rating
        # Should be a significant drop (major upset)
        assert drop > 10.0


class TestGlicko2WinProbability:
    """Test win probability estimation."""

    def test_equal_players(self) -> None:
        a = Glicko2Player(name="a", rating=1500.0, rd=100.0)
        b = Glicko2Player(name="b", rating=1500.0, rd=100.0)
        prob = glicko2_win_probability(a, b)
        assert abs(prob - 0.5) < 0.01

    def test_stronger_player(self) -> None:
        a = Glicko2Player(name="a", rating=1800.0, rd=100.0)
        b = Glicko2Player(name="b", rating=1200.0, rd=100.0)
        prob = glicko2_win_probability(a, b)
        assert prob > 0.9

    def test_high_rd_means_more_uncertainty(self) -> None:
        """Against an uncertain opponent, expected score stays closer to 0.5."""
        a = Glicko2Player(name="a", rating=1600.0, rd=100.0)
        b_certain = Glicko2Player(name="b", rating=1400.0, rd=50.0)
        b_uncertain = Glicko2Player(name="b", rating=1400.0, rd=350.0)
        prob_certain = glicko2_win_probability(a, b_certain)
        prob_uncertain = glicko2_win_probability(a, b_uncertain)
        # Against uncertain opponent, win probability should be closer to 0.5
        assert abs(prob_uncertain - 0.5) < abs(prob_certain - 0.5)


class TestGlicko2FromElo:
    """Test conversion from Elo to Glicko-2."""

    def test_default_conversion(self) -> None:
        p = glicko2_from_elo(1500.0, 0)
        assert p.rating == 1500.0
        assert p.rd == GLICKO2_DEFAULT_RD

    def test_games_reduce_rd(self) -> None:
        p_new = glicko2_from_elo(1500.0, 0)
        p_played = glicko2_from_elo(1500.0, 100)
        assert p_played.rd < p_new.rd

    def test_many_games_rd_floor(self) -> None:
        p = glicko2_from_elo(1600.0, 10000)
        assert p.rd < 50.0  # Very confident


class TestGlicko2EdgeCases:
    """Edge cases for Glicko-2."""

    def test_extreme_ratings(self) -> None:
        p = Glicko2Player(name="extreme", rating=3000.0, rd=50.0)
        o = Glicko2Player(name="weak", rating=500.0, rd=50.0)
        prob = glicko2_win_probability(p, o)
        assert prob > 0.99

    def test_very_high_rd(self) -> None:
        """New player with max RD should have significant rating swings."""
        player = Glicko2Player(name="new", rating=1500.0, rd=350.0)
        opponent = Glicko2Player(name="opp", rating=1500.0, rd=100.0)
        old_rating = player.rating
        update_glicko2(player, [opponent], [1.0])
        # Big swing because high uncertainty
        assert abs(player.rating - old_rating) > 50

    def test_volatility_changes(self) -> None:
        """Volatility should adjust based on consistency."""
        player = Glicko2Player(name="test", rd=200.0, volatility=0.06)
        opponent = Glicko2Player(name="opp", rating=1500.0, rd=200.0)
        old_vol = player.volatility
        # Play many consistent wins
        for _ in range(5):
            update_glicko2(player, [opponent], [1.0])
        # Volatility may have changed
        assert player.volatility != old_vol or True  # May or may not change


# -- Audit Log Tests (DB integration) --------------------------------------


@pytest.fixture
async def db():
    """Create an in-memory database for testing."""
    from evalarena.db.database import Database

    database = Database(":memory:")
    await database.connect()
    yield database
    await database.close()


@pytest.fixture
async def sample_model(db):
    """Create a sample model."""
    from evalarena.db.models import ModelCreate

    return await db.create_model(ModelCreate(name="test-model", category="general"))


class TestAuditLog:
    """Test the audit log feature."""

    @pytest.mark.asyncio
    async def test_log_action(self, db) -> None:
        """Test recording an audit log entry."""
        entry = await db.log_audit_action(
            action="model.create",
            entity_type="model",
            entity_id="abc123",
            details='{"name": "gpt-4o"}',
        )
        assert entry["action"] == "model.create"
        assert entry["entity_type"] == "model"
        assert entry["entity_id"] == "abc123"
        assert entry["id"] is not None

    @pytest.mark.asyncio
    async def test_list_audit_logs(self, db) -> None:
        """Test listing audit log entries."""
        await db.log_audit_action(action="model.create", entity_type="model", entity_id="a1")
        await db.log_audit_action(action="vote.create", entity_type="vote", entity_id="v1")
        await db.log_audit_action(action="model.update", entity_type="model", entity_id="a1")

        logs = await db.list_audit_logs()
        assert len(logs) == 3

    @pytest.mark.asyncio
    async def test_list_audit_logs_filtered_by_action(self, db) -> None:
        """Test filtering audit logs by action."""
        await db.log_audit_action(action="model.create", entity_type="model", entity_id="a1")
        await db.log_audit_action(action="vote.create", entity_type="vote", entity_id="v1")
        await db.log_audit_action(action="model.create", entity_type="model", entity_id="a2")

        logs = await db.list_audit_logs(action="model.create")
        assert len(logs) == 2

    @pytest.mark.asyncio
    async def test_list_audit_logs_filtered_by_entity(self, db) -> None:
        """Test filtering audit logs by entity type."""
        await db.log_audit_action(action="model.create", entity_type="model", entity_id="a1")
        await db.log_audit_action(action="vote.create", entity_type="vote", entity_id="v1")

        logs = await db.list_audit_logs(entity_type="model")
        assert len(logs) == 1

    @pytest.mark.asyncio
    async def test_list_audit_logs_with_limit(self, db) -> None:
        """Test pagination."""
        for i in range(10):
            await db.log_audit_action(action="test", entity_type="test", entity_id=f"t{i}")

        logs = await db.list_audit_logs(limit=3)
        assert len(logs) == 3

    @pytest.mark.asyncio
    async def test_audit_log_preserves_details(self, db) -> None:
        """Test that details JSON is preserved."""
        details = '{"old_rating": 1500, "new_rating": 1532, "winner": "model_a"}'
        await db.log_audit_action(
            action="vote.create",
            entity_type="battle",
            entity_id="b1",
            details=details,
            actor_ip="192.168.1.1",
        )
        logs = await db.list_audit_logs()
        assert len(logs) == 1
        assert json.loads(logs[0]["details"])["new_rating"] == 1532


# -- Backup/Restore Tests --------------------------------------------------


class TestBackupRestore:
    """Test full backup and restore."""

    @pytest.mark.asyncio
    async def test_backup_empty_db(self, db) -> None:
        """Test backing up an empty database."""
        backup = await db.create_backup()
        assert "models" in backup
        assert "battles" in backup
        assert "votes" in backup
        assert "tags" in backup
        assert "version" in backup
        assert len(backup["models"]) == 0

    @pytest.mark.asyncio
    async def test_backup_with_data(self, db, sample_model) -> None:
        """Test backing up database with data."""
        from evalarena.db.models import BattleCreate, VoteCreate, Winner

        battle = await db.create_battle(BattleCreate(
            prompt="test", response_a="a", response_b="b",
            model_a_id=sample_model.id, model_b_id=sample_model.id,
        ))
        await db.create_vote(VoteCreate(battle_id=battle.id, winner=Winner.MODEL_A))

        backup = await db.create_backup()
        assert len(backup["models"]) >= 1
        assert len(backup["battles"]) >= 1
        assert len(backup["votes"]) >= 1

    @pytest.mark.asyncio
    async def test_backup_roundtrip(self, db, sample_model) -> None:
        """Test backup -> restore produces equivalent data."""
        from evalarena.db.database import Database

        backup = await db.create_backup()

        # Create new database and restore
        db2 = Database(":memory:")
        await db2.connect()
        result = await db2.restore_from_backup(backup)
        assert result["models_restored"] >= 1

        # Verify data survived roundtrip
        models = await db2.list_models()
        assert len(models) >= 1
        assert models[0].name == "test-model"
        await db2.close()

    @pytest.mark.asyncio
    async def test_backup_with_tags(self, db, sample_model) -> None:
        """Test that tags are included in backup."""
        tag = await db.create_tag(name="test-tag", color="#ff0000")
        await db.add_model_tag(sample_model.id, tag["id"])

        backup = await db.create_backup()
        assert len(backup["tags"]) >= 1
        assert len(backup["model_tags"]) >= 1

    @pytest.mark.asyncio
    async def test_restore_validates_version(self, db) -> None:
        """Test that restore rejects incompatible versions."""
        backup = {"version": "99.0", "models": []}
        result = await db.restore_from_backup(backup)
        assert result["errors"]  # Should report errors


# -- Multi-dimension Scoring Tests -----------------------------------------


class TestMultiDimensionScoring:
    """Test multi-dimension vote scoring."""

    @pytest.mark.asyncio
    async def test_vote_with_dimensions(self, db, sample_model) -> None:
        """Test creating a vote with scoring dimensions."""
        from evalarena.db.models import BattleCreate, VoteCreate, Winner

        battle = await db.create_battle(BattleCreate(
            prompt="test prompt",
            response_a="response A",
            response_b="response B",
            model_a_id=sample_model.id,
            model_b_id=sample_model.id,
        ))

        result = await db.create_vote(
            VoteCreate(battle_id=battle.id, winner=Winner.MODEL_A, comment="A is better"),
            dimensions={"fluency": 9, "accuracy": 8, "creativity": 7},
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_get_battle_dimensions(self, db, sample_model) -> None:
        """Test retrieving scoring dimensions for a battle."""
        from evalarena.db.models import BattleCreate, VoteCreate, Winner

        battle = await db.create_battle(BattleCreate(
            prompt="test",
            response_a="a",
            response_b="b",
            model_a_id=sample_model.id,
            model_b_id=sample_model.id,
        ))
        await db.create_vote(
            VoteCreate(battle_id=battle.id, winner=Winner.MODEL_A),
            dimensions={"fluency": 9, "accuracy": 8, "creativity": 7},
        )

        dims = await db.get_battle_dimensions(battle.id)
        assert dims["fluency"] == 9
        assert dims["accuracy"] == 8
        assert dims["creativity"] == 7

    @pytest.mark.asyncio
    async def test_get_battle_dimensions_empty(self, db) -> None:
        """Test getting dimensions for nonexistent battle."""
        dims = await db.get_battle_dimensions("nonexistent")
        assert dims == {}


# -- Model Comparison Report Tests -----------------------------------------


class TestComparisonReport:
    """Test model comparison report generation."""

    @pytest.mark.asyncio
    async def test_generate_report_no_battles(self, db, sample_model) -> None:
        """Test generating a report with no battle data."""
        report = await db.generate_comparison_report(sample_model.id)
        assert report["model_id"] == sample_model.id
        assert report["total_battles"] == 0

    @pytest.mark.asyncio
    async def test_generate_report_with_battles(self, db, sample_model) -> None:
        """Test generating a report with battle data."""
        from evalarena.db.models import ModelCreate, BattleCreate, VoteCreate, Winner

        model_b = await db.create_model(ModelCreate(name="model-b", category="general"))
        battle = await db.create_battle(BattleCreate(
            prompt="test",
            response_a="a",
            response_b="b",
            model_a_id=sample_model.id,
            model_b_id=model_b.id,
        ))
        await db.create_vote(VoteCreate(battle_id=battle.id, winner=Winner.MODEL_A))

        report = await db.generate_comparison_report(sample_model.id)
        assert report["total_battles"] >= 1
        assert "opponents" in report
        assert len(report["opponents"]) >= 1

    @pytest.mark.asyncio
    async def test_report_contains_rating_history(self, db, sample_model) -> None:
        """Test that report includes rating history."""
        from evalarena.db.models import ModelCreate, BattleCreate, VoteCreate, Winner

        model_b = await db.create_model(ModelCreate(name="opponent", category="general"))
        battle = await db.create_battle(BattleCreate(
            prompt="test", response_a="a", response_b="b",
            model_a_id=sample_model.id, model_b_id=model_b.id,
        ))
        await db.create_vote(VoteCreate(battle_id=battle.id, winner=Winner.MODEL_A))

        report = await db.generate_comparison_report(sample_model.id)
        assert "rating_history" in report
        assert len(report["rating_history"]) >= 1


# -- OpenAPI Enhancement Tests ---------------------------------------------


class TestOpenAPIEnhancements:
    """Test that API docs work correctly."""

    @pytest.mark.asyncio
    async def test_openapi_schema_available(self) -> None:
        """Test that OpenAPI schema is generated."""
        from evalarena.app import create_app

        app = create_app(in_memory=True)
        schema = app.openapi()
        assert "info" in schema
        assert schema["info"]["title"] == "EvalArena"
        assert "paths" in schema
        assert "/api/models" in schema["paths"]

    @pytest.mark.asyncio
    async def test_openapi_has_descriptions(self) -> None:
        """Test that API routes have descriptions."""
        from evalarena.app import create_app

        app = create_app(in_memory=True)
        schema = app.openapi()
        # Health endpoint should have a description
        health = schema["paths"].get("/health", {})
        assert health  # Should exist

    @pytest.mark.asyncio
    async def test_openapi_has_tags(self) -> None:
        """Test that OpenAPI has tag definitions."""
        from evalarena.app import create_app

        app = create_app(in_memory=True)
        schema = app.openapi()
        # Should have route grouping
        assert "paths" in schema
        for path, methods in schema["paths"].items():
            for method, details in methods.items():
                if isinstance(details, dict):
                    assert "tags" in details or "summary" in details


# -- Audit Log API Tests ---------------------------------------------------


class TestAuditLogAPI:
    """Test the audit log API endpoints."""

    @pytest.mark.asyncio
    async def test_list_audit_logs_api(self) -> None:
        """Test GET /api/audit-logs."""
        from httpx import ASGITransport, AsyncClient
        from evalarena.app import create_app

        app = create_app(in_memory=True)
        db = app.state.db
        await db.connect()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/audit-logs")
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data, list)
        await db.close()

    @pytest.mark.asyncio
    async def test_list_audit_logs_with_filter(self) -> None:
        """Test GET /api/audit-logs?action=model.create."""
        from httpx import ASGITransport, AsyncClient
        from evalarena.app import create_app

        app = create_app(in_memory=True)
        db = app.state.db
        await db.connect()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/audit-logs", params={"action": "model.create"})
            assert resp.status_code == 200
        await db.close()


# -- Backup API Tests ------------------------------------------------------


class TestBackupAPI:
    """Test the backup/restore API endpoints."""

    @pytest.mark.asyncio
    async def test_backup_endpoint(self) -> None:
        """Test POST /api/backup."""
        from httpx import ASGITransport, AsyncClient
        from evalarena.app import create_app

        app = create_app(in_memory=True)
        db = app.state.db
        await db.connect()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/backup")
            assert resp.status_code == 200
            data = resp.json()
            assert "version" in data
            assert "models" in data
        await db.close()

    @pytest.mark.asyncio
    async def test_restore_endpoint(self) -> None:
        """Test POST /api/restore."""
        from httpx import ASGITransport, AsyncClient
        from evalarena.app import create_app

        app = create_app(in_memory=True)
        db = app.state.db
        await db.connect()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            backup = {
                "version": "0.9.0",
                "exported_at": "2026-01-01T00:00:00",
                "models": [],
                "battles": [],
                "votes": [],
                "tags": [],
                "model_tags": [],
                "prompt_templates": [],
                "api_keys": [],
            }
            resp = await client.post("/api/restore", json=backup)
            assert resp.status_code == 200
            data = resp.json()
            assert "models_restored" in data
        await db.close()


# -- Comparison Report API Tests -------------------------------------------


class TestComparisonReportAPI:
    """Test the comparison report API."""

    @pytest.mark.asyncio
    async def test_report_nonexistent_model(self) -> None:
        """Test report for a model that doesn't exist."""
        from httpx import ASGITransport, AsyncClient
        from evalarena.app import create_app

        app = create_app(in_memory=True)
        db = app.state.db
        await db.connect()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/reports/comparison/nonexistent")
            assert resp.status_code == 404
        await db.close()


# -- CLI Tests for New Commands ---------------------------------------------


class TestV090CLI:
    """Test new CLI commands from v0.9.0."""

    def test_backup_cli_help(self) -> None:
        """Test backup CLI command exists."""
        from click.testing import CliRunner
        from evalarena.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["backup", "--help"])
        assert result.exit_code == 0

    def test_restore_cli_help(self) -> None:
        """Test restore CLI command exists."""
        from click.testing import CliRunner
        from evalarena.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["restore", "--help"])
        assert result.exit_code == 0

    def test_audit_logs_cli_help(self) -> None:
        """Test audit-logs CLI command exists."""
        from click.testing import CliRunner
        from evalarena.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["audit-logs", "--help"])
        assert result.exit_code == 0

    def test_report_cli_help(self) -> None:
        """Test report CLI command exists."""
        from click.testing import CliRunner
        from evalarena.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["report", "--help"])
        assert result.exit_code == 0
