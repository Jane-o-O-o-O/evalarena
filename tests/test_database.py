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

# -- Confidence Interval in Model/Leaderboard ---------------------------


@pytest.mark.asyncio
async def test_model_has_ci(db: Database):
    """Model output should include confidence interval."""
    m = await db.create_model(ModelCreate(name="ci-test"))
    assert m.ci_lower == 600.0
    assert m.ci_upper == 1400.0


@pytest.mark.asyncio
async def test_leaderboard_has_ci(db: Database):
    """Leaderboard entries should include confidence interval."""
    m = await db.create_model(ModelCreate(name="lb-ci"))
    lb = await db.get_leaderboard()
    assert len(lb) == 1
    assert lb[0].ci_lower < lb[0].rating < lb[0].ci_upper


@pytest.mark.asyncio
async def test_ci_narrows_with_games(db: Database):
    """CI should narrow as more games are played."""
    a = await db.create_model(ModelCreate(name="a"))
    b = await db.create_model(ModelCreate(name="b"))
    # Play 10 games
    for i in range(10):
        battle = await db.create_battle(
            BattleCreate(
                prompt=f"q{i}", response_a="a", response_b="b",
                model_a_id=a.id, model_b_id=b.id,
            )
        )
        await db.create_vote(VoteCreate(battle_id=battle.id, winner=Winner.MODEL_A))
    a_after = await db.get_model(a.id)
    ci_width = a_after.ci_upper - a_after.ci_lower
    assert ci_width < 800  # Much narrower than 1000.0 for 0 games


# -- Match History -------------------------------------------------------


@pytest.mark.asyncio
async def test_get_model_battles(db: Database):
    """Should return all battles involving a model."""
    a = await db.create_model(ModelCreate(name="hist-a"))
    b = await db.create_model(ModelCreate(name="hist-b"))
    battle = await db.create_battle(
        BattleCreate(
            prompt="test prompt", response_a="a", response_b="b",
            model_a_id=a.id, model_b_id=b.id,
        )
    )
    await db.create_vote(VoteCreate(battle_id=battle.id, winner=Winner.MODEL_A))

    battles = await db.get_model_battles(a.id)
    assert len(battles) == 1
    assert battles[0].opponent_name == "hist-b"
    assert battles[0].result == "win"


@pytest.mark.asyncio
async def test_get_model_battles_loss(db: Database):
    """Should correctly identify losses."""
    a = await db.create_model(ModelCreate(name="loser"))
    b = await db.create_model(ModelCreate(name="winner"))
    battle = await db.create_battle(
        BattleCreate(
            prompt="q", response_a="a", response_b="b",
            model_a_id=a.id, model_b_id=b.id,
        )
    )
    await db.create_vote(VoteCreate(battle_id=battle.id, winner=Winner.MODEL_B))

    battles = await db.get_model_battles(a.id)
    assert battles[0].result == "loss"


@pytest.mark.asyncio
async def test_get_model_battles_tie(db: Database):
    """Should correctly identify ties."""
    a = await db.create_model(ModelCreate(name="tie-a"))
    b = await db.create_model(ModelCreate(name="tie-b"))
    battle = await db.create_battle(
        BattleCreate(
            prompt="q", response_a="a", response_b="b",
            model_a_id=a.id, model_b_id=b.id,
        )
    )
    await db.create_vote(VoteCreate(battle_id=battle.id, winner=Winner.TIE))

    battles = await db.get_model_battles(a.id)
    assert battles[0].result == "tie"


@pytest.mark.asyncio
async def test_get_model_battles_empty(db: Database):
    """Should return empty list for model with no battles."""
    a = await db.create_model(ModelCreate(name="lonely"))
    battles = await db.get_model_battles(a.id)
    assert battles == []


@pytest.mark.asyncio
async def test_get_model_battles_pagination(db: Database):
    """Should support limit and offset."""
    a = await db.create_model(ModelCreate(name="pag-a"))
    b = await db.create_model(ModelCreate(name="pag-b"))
    for i in range(5):
        await db.create_battle(
            BattleCreate(
                prompt=f"q{i}", response_a="a", response_b="b",
                model_a_id=a.id, model_b_id=b.id,
            )
        )
    battles = await db.get_model_battles(a.id, limit=2, offset=1)
    assert len(battles) == 2


# -- Head-to-Head --------------------------------------------------------


@pytest.mark.asyncio
async def test_head_to_head(db: Database):
    """Should return correct head-to-head stats."""
    a = await db.create_model(ModelCreate(name="h2h-a"))
    b = await db.create_model(ModelCreate(name="h2h-b"))

    # a wins 2, b wins 1, 1 tie
    for i in range(2):
        battle = await db.create_battle(
            BattleCreate(
                prompt=f"q{i}", response_a="a", response_b="b",
                model_a_id=a.id, model_b_id=b.id,
            )
        )
        await db.create_vote(VoteCreate(battle_id=battle.id, winner=Winner.MODEL_A))

    battle = await db.create_battle(
        BattleCreate(
            prompt="q2", response_a="a", response_b="b",
            model_a_id=a.id, model_b_id=b.id,
        )
    )
    await db.create_vote(VoteCreate(battle_id=battle.id, winner=Winner.MODEL_B))

    battle = await db.create_battle(
        BattleCreate(
            prompt="q3", response_a="a", response_b="b",
            model_a_id=a.id, model_b_id=b.id,
        )
    )
    await db.create_vote(VoteCreate(battle_id=battle.id, winner=Winner.TIE))

    h2h = await db.head_to_head(a.id, b.id)
    assert h2h.model_a == "h2h-a"
    assert h2h.model_b == "h2h-b"
    assert h2h.model_a_wins == 2
    assert h2h.model_b_wins == 1
    assert h2h.ties == 1
    assert h2h.total_battles == 4
    assert h2h.model_a_win_rate == 50.0


@pytest.mark.asyncio
async def test_head_to_head_no_battles(db: Database):
    """Should return zero stats when no battles between models."""
    a = await db.create_model(ModelCreate(name="empty-a"))
    b = await db.create_model(ModelCreate(name="empty-b"))

    h2h = await db.head_to_head(a.id, b.id)
    assert h2h.total_battles == 0
    assert h2h.model_a_win_rate == 0.0


@pytest.mark.asyncio
async def test_head_to_head_nonexistent(db: Database):
    """Should raise ValueError for nonexistent model."""
    a = await db.create_model(ModelCreate(name="real"))
    with pytest.raises(ValueError):
        await db.head_to_head(a.id, "fake")


# -- Stats ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_stats(db: Database):
    """Should return aggregate stats."""
    a = await db.create_model(ModelCreate(name="s-a"))
    b = await db.create_model(ModelCreate(name="s-b"))
    battle = await db.create_battle(
        BattleCreate(
            prompt="q", response_a="a", response_b="b",
            model_a_id=a.id, model_b_id=b.id,
        )
    )
    await db.create_vote(VoteCreate(battle_id=battle.id, winner=Winner.MODEL_A))

    stats = await db.get_stats()
    assert stats.total_models == 2
    assert stats.total_battles == 1
    assert stats.total_votes == 1
    assert stats.avg_rating > 0
    assert stats.highest_rating >= stats.lowest_rating


@pytest.mark.asyncio
async def test_get_stats_empty(db: Database):
    """Should handle empty database."""
    stats = await db.get_stats()
    assert stats.total_models == 0
    assert stats.total_battles == 0
    assert stats.total_votes == 0


@pytest.mark.asyncio
async def test_count_votes(db: Database):
    """Should count votes correctly."""
    assert await db.count_votes() == 0
    a = await db.create_model(ModelCreate(name="v-a"))
    b = await db.create_model(ModelCreate(name="v-b"))
    battle = await db.create_battle(
        BattleCreate(
            prompt="q", response_a="a", response_b="b",
            model_a_id=a.id, model_b_id=b.id,
        )
    )
    await db.create_vote(VoteCreate(battle_id=battle.id, winner=Winner.MODEL_A))
    assert await db.count_votes() == 1


# -- Model Detail ---------------------------------------------------------


@pytest.mark.asyncio
async def test_get_model_detail(db: Database):
    """Should return model detail with match history."""
    a = await db.create_model(ModelCreate(name="detail-a"))
    b = await db.create_model(ModelCreate(name="detail-b"))
    battle = await db.create_battle(
        BattleCreate(
            prompt="detailed prompt", response_a="a", response_b="b",
            model_a_id=a.id, model_b_id=b.id,
        )
    )
    await db.create_vote(VoteCreate(battle_id=battle.id, winner=Winner.MODEL_A))

    detail = await db.get_model_detail(a.id)
    assert detail is not None
    assert detail.name == "detail-a"
    assert detail.total_games == 1
    assert detail.wins == 1
    assert len(detail.recent_battles) == 1
    assert detail.recent_battles[0].result == "win"


@pytest.mark.asyncio
async def test_get_model_detail_not_found(db: Database):
    """Should return None for nonexistent model."""
    assert await db.get_model_detail("nonexistent") is None


# -- List battles with unvoted filter -------------------------------------


@pytest.mark.asyncio
async def test_list_battles_unvoted_only(db: Database):
    """Should filter to only unvoted battles."""
    a = await db.create_model(ModelCreate(name="f-a"))
    b = await db.create_model(ModelCreate(name="f-b"))
    # Create 3 battles, vote on 1
    for i in range(3):
        await db.create_battle(
            BattleCreate(
                prompt=f"q{i}", response_a="a", response_b="b",
                model_a_id=a.id, model_b_id=b.id,
            )
        )
    battles = await db.list_battles()
    battle_id = battles[0].id
    await db.create_vote(VoteCreate(battle_id=battle_id, winner=Winner.MODEL_A))

    unvoted = await db.list_battles(unvoted_only=True)
    assert len(unvoted) == 2
    all_battles = await db.list_battles(unvoted_only=False)
    assert len(all_battles) == 3


@pytest.mark.asyncio
async def test_battle_out_has_voted_field(db: Database):
    """BattleOut should include voted field."""
    a = await db.create_model(ModelCreate(name="vf-a"))
    b = await db.create_model(ModelCreate(name="vf-b"))
    battle = await db.create_battle(
        BattleCreate(
            prompt="q", response_a="a", response_b="b",
            model_a_id=a.id, model_b_id=b.id,
        )
    )
    battles = await db.list_battles()
    assert battles[0].voted is False

    await db.create_vote(VoteCreate(battle_id=battle.id, winner=Winner.MODEL_A))
    battles = await db.list_battles()
    assert battles[0].voted is True
