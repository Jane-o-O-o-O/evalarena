"""Tests for database layer — full CRUD flow."""

import pytest
import pytest_asyncio

from evalarena.db.database import Database
from evalarena.db.models import (
    BattleCreate,
    LeaderboardEntry,
    ModelCreate,
    VoteCreate,
    Winner,
)


@pytest_asyncio.fixture
async def db():
    """In-memory database for testing."""
    database = Database(":memory:")
    await database.connect()
    yield database
    await database.close()


# ── Models ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_model(db: Database):
    m = await db.create_model(ModelCreate(name="gpt-4o"))
    assert m.name == "gpt-4o"
    assert m.rating == 1000.0
    assert m.id


@pytest.mark.asyncio
async def test_create_duplicate_model_fails(db: Database):
    await db.create_model(ModelCreate(name="gpt-4o"))
    with pytest.raises(Exception):  # UNIQUE constraint
        await db.create_model(ModelCreate(name="gpt-4o"))


@pytest.mark.asyncio
async def test_get_model(db: Database):
    m = await db.create_model(ModelCreate(name="claude-3"))
    found = await db.get_model(m.id)
    assert found is not None
    assert found.name == "claude-3"


@pytest.mark.asyncio
async def test_get_model_not_found(db: Database):
    assert await db.get_model("nonexistent") is None


@pytest.mark.asyncio
async def test_get_model_by_name(db: Database):
    await db.create_model(ModelCreate(name="llama-3"))
    found = await db.get_model_by_name("llama-3")
    assert found is not None
    assert found.name == "llama-3"


@pytest.mark.asyncio
async def test_list_models(db: Database):
    await db.create_model(ModelCreate(name="a"))
    await db.create_model(ModelCreate(name="b"))
    models = await db.list_models()
    assert len(models) == 2


@pytest.mark.asyncio
async def test_delete_model(db: Database):
    m = await db.create_model(ModelCreate(name="to-delete"))
    assert await db.delete_model(m.id) is True
    assert await db.get_model(m.id) is None


@pytest.mark.asyncio
async def test_delete_model_not_found(db: Database):
    assert await db.delete_model("nonexistent") is False


# ── Battles ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_battle(db: Database):
    a = await db.create_model(ModelCreate(name="model-a"))
    b = await db.create_model(ModelCreate(name="model-b"))
    battle = await db.create_battle(
        BattleCreate(
            prompt="What is AI?",
            response_a="AI is artificial intelligence.",
            response_b="AI stands for artificial intelligence.",
            model_a_id=a.id,
            model_b_id=b.id,
        )
    )
    assert battle.id
    assert battle.prompt == "What is AI?"
    assert battle.response_a == "AI is artificial intelligence."


@pytest.mark.asyncio
async def test_get_battle(db: Database):
    a = await db.create_model(ModelCreate(name="m1"))
    b = await db.create_model(ModelCreate(name="m2"))
    battle = await db.create_battle(
        BattleCreate(
            prompt="test",
            response_a="resp a",
            response_b="resp b",
            model_a_id=a.id,
            model_b_id=b.id,
        )
    )
    found = await db.get_battle(battle.id)
    assert found is not None
    assert found["prompt"] == "test"
    assert found["model_a_id"] == a.id


@pytest.mark.asyncio
async def test_list_battles(db: Database):
    a = await db.create_model(ModelCreate(name="x"))
    b = await db.create_model(ModelCreate(name="y"))
    for i in range(3):
        await db.create_battle(
            BattleCreate(
                prompt=f"q{i}",
                response_a=f"a{i}",
                response_b=f"b{i}",
                model_a_id=a.id,
                model_b_id=b.id,
            )
        )
    battles = await db.list_battles()
    assert len(battles) == 3


# ── Voting + ELO ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_vote_updates_elo(db: Database):
    a = await db.create_model(ModelCreate(name="winner-model"))
    b = await db.create_model(ModelCreate(name="loser-model"))
    battle = await db.create_battle(
        BattleCreate(
            prompt="test",
            response_a="good answer",
            response_b="bad answer",
            model_a_id=a.id,
            model_b_id=b.id,
        )
    )
    result = await db.create_vote(VoteCreate(battle_id=battle.id, winner=Winner.MODEL_A))
    assert result is True

    # Check ratings updated
    a_after = await db.get_model(a.id)
    b_after = await db.get_model(b.id)
    assert a_after is not None and b_after is not None
    assert a_after.rating > 1000.0
    assert b_after.rating < 1000.0
    assert a_after.wins == 1
    assert b_after.losses == 1


@pytest.mark.asyncio
async def test_vote_tie(db: Database):
    a = await db.create_model(ModelCreate(name="tie-a"))
    b = await db.create_model(ModelCreate(name="tie-b"))
    battle = await db.create_battle(
        BattleCreate(
            prompt="q",
            response_a="a",
            response_b="b",
            model_a_id=a.id,
            model_b_id=b.id,
        )
    )
    await db.create_vote(VoteCreate(battle_id=battle.id, winner=Winner.TIE))
    a_after = await db.get_model(a.id)
    b_after = await db.get_model(b.id)
    assert a_after is not None and b_after is not None
    assert a_after.ties == 1
    assert b_after.ties == 1


@pytest.mark.asyncio
async def test_double_vote_rejected(db: Database):
    a = await db.create_model(ModelCreate(name="a"))
    b = await db.create_model(ModelCreate(name="b"))
    battle = await db.create_battle(
        BattleCreate(
            prompt="q",
            response_a="a",
            response_b="b",
            model_a_id=a.id,
            model_b_id=b.id,
        )
    )
    assert await db.create_vote(VoteCreate(battle_id=battle.id, winner=Winner.MODEL_A)) is True
    assert await db.create_vote(VoteCreate(battle_id=battle.id, winner=Winner.MODEL_B)) is False


@pytest.mark.asyncio
async def test_vote_nonexistent_battle(db: Database):
    with pytest.raises(ValueError, match="not found"):
        await db.create_vote(VoteCreate(battle_id="ghost", winner=Winner.MODEL_A))


# ── Leaderboard ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_leaderboard_sorted_by_rating(db: Database):
    a = await db.create_model(ModelCreate(name="alpha"))
    b = await db.create_model(ModelCreate(name="beta"))
    c = await db.create_model(ModelCreate(name="gamma"))

    # a beats b
    battle1 = await db.create_battle(
        BattleCreate(prompt="q", response_a="a", response_b="b", model_a_id=a.id, model_b_id=b.id)
    )
    await db.create_vote(VoteCreate(battle_id=battle1.id, winner=Winner.MODEL_A))

    # c beats b
    battle2 = await db.create_battle(
        BattleCreate(prompt="q", response_a="c", response_b="b", model_a_id=c.id, model_b_id=b.id)
    )
    await db.create_vote(VoteCreate(battle_id=battle2.id, winner=Winner.MODEL_A))

    lb = await db.get_leaderboard()
    assert len(lb) == 3
    # a and c should be ranked 1 and 2 (both beat b)
    assert lb[0].rating >= lb[1].rating >= lb[2].rating
    assert lb[0].rank == 1


@pytest.mark.asyncio
async def test_leaderboard_empty(db: Database):
    lb = await db.get_leaderboard()
    assert len(lb) == 0


@pytest.mark.asyncio
async def test_count_models(db: Database):
    assert await db.count_models() == 0
    await db.create_model(ModelCreate(name="a"))
    assert await db.count_models() == 1


@pytest.mark.asyncio
async def test_count_battles(db: Database):
    a = await db.create_model(ModelCreate(name="a"))
    b = await db.create_model(ModelCreate(name="b"))
    assert await db.count_battles() == 0
    await db.create_battle(
        BattleCreate(prompt="q", response_a="a", response_b="b", model_a_id=a.id, model_b_id=b.id)
    )
    assert await db.count_battles() == 1
