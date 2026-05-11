"""Tests for ELO rating system."""

import pytest

from evalarena.core.elo import (
    ModelRating,
    calculate_elo_update,
    expected_score,
    update_ratings,
)


class TestExpectedScore:
    """Tests for the expected score calculation."""

    def test_equal_ratings_give_half(self):
        assert expected_score(1000, 1000) == pytest.approx(0.5)

    def test_higher_rating_gives_higher_expected(self):
        assert expected_score(1400, 1000) > 0.9

    def test_lower_rating_gives_lower_expected(self):
        assert expected_score(1000, 1400) < 0.1

    def test_expected_scores_sum_to_one(self):
        a = expected_score(1200, 1000)
        b = expected_score(1000, 1200)
        assert a + b == pytest.approx(1.0)

    def test_big_gap_saturates(self):
        """Very large rating gap -> expected score approaches 1."""
        assert expected_score(2000, 800) > 0.99


class TestCalculateEloUpdate:
    """Tests for ELO update calculation."""

    def test_equal_ratings_winner_gains(self):
        result = calculate_elo_update(1000, 1000, k_factor=32)
        assert result.winner_new_rating > 1000
        assert result.loser_new_rating < 1000

    def test_equal_ratings_gain_equals_loss(self):
        result = calculate_elo_update(1000, 1000, k_factor=32)
        gain = result.winner_new_rating - 1000
        loss = 1000 - result.loser_new_rating
        assert gain == pytest.approx(loss)

    def test_k_factor_scaling(self):
        r1 = calculate_elo_update(1000, 1000, k_factor=16)
        r2 = calculate_elo_update(1000, 1000, k_factor=32)
        gain1 = r1.winner_new_rating - 1000
        gain2 = r2.winner_new_rating - 1000
        assert gain2 == pytest.approx(gain1 * 2)

    def test_upset_bigger_gain(self):
        """When a lower-rated player wins, they gain more."""
        r_upset = calculate_elo_update(800, 1200, k_factor=32)
        r_expected = calculate_elo_update(1200, 800, k_factor=32)
        assert (r_upset.winner_new_rating - 800) > (r_expected.winner_new_rating - 1200)

    def test_tie_gives_half_expected(self):
        result = calculate_elo_update(1000, 1000, k_factor=32, is_tie=True)
        # Equal ratings, tie -> no change
        assert result.winner_new_rating == pytest.approx(1000)
        assert result.loser_new_rating == pytest.approx(1000)

    def test_tie_unequal_ratings(self):
        """Higher-rated player loses points on a tie with a weaker player."""
        result = calculate_elo_update(1200, 1000, k_factor=32, is_tie=True)
        assert result.winner_new_rating < 1200  # "winner" (model_a) expected to win, so loses
        assert result.loser_new_rating > 1000    # "loser" (model_b) gains from tie

    def test_expected_score_in_result(self):
        result = calculate_elo_update(1200, 1000, k_factor=32)
        assert 0 < result.expected_winner < 1
        assert result.expected_winner + result.expected_loser == pytest.approx(1.0)


class TestModelRating:
    """Tests for the ModelRating dataclass."""

    def test_default_values(self):
        m = ModelRating(name="gpt-4")
        assert m.rating == 1000.0
        assert m.wins == 0
        assert m.losses == 0
        assert m.ties == 0

    def test_total_games(self):
        m = ModelRating(name="test", wins=5, losses=3, ties=2)
        assert m.total_games == 10

    def test_win_rate(self):
        m = ModelRating(name="test", wins=7, losses=3, ties=0)
        assert m.win_rate == pytest.approx(70.0)

    def test_win_rate_no_games(self):
        m = ModelRating(name="test")
        assert m.win_rate == 0.0


class TestUpdateRatings:
    """Tests for the update_ratings in-place function."""

    def test_winner_gains_rating(self):
        a = ModelRating(name="a")
        b = ModelRating(name="b")
        update_ratings(a, b, "battle-1")
        assert a.rating > 1000.0
        assert b.rating < 1000.0

    def test_stats_updated_win(self):
        a = ModelRating(name="a")
        b = ModelRating(name="b")
        update_ratings(a, b, "battle-1")
        assert a.wins == 1
        assert a.losses == 0
        assert b.losses == 1
        assert b.wins == 0

    def test_stats_updated_tie(self):
        a = ModelRating(name="a")
        b = ModelRating(name="b")
        update_ratings(a, b, "battle-1", is_tie=True)
        assert a.ties == 1
        assert b.ties == 1
        assert a.wins == 0
        assert b.wins == 0

    def test_battle_ids_tracked(self):
        a = ModelRating(name="a")
        b = ModelRating(name="b")
        update_ratings(a, b, "battle-xyz")
        assert "battle-xyz" in a.battle_ids
        assert "battle-xyz" in b.battle_ids

    def test_convergence_over_many_games(self):
        """A stronger model (wins every game) should converge to higher rating."""
        strong = ModelRating(name="strong")
        weak = ModelRating(name="weak")
        for i in range(100):
            update_ratings(strong, weak, f"b-{i}")
        # ELO converges against the same opponent; 100 games -> ~300 pt gap
        assert strong.rating > 1200
        assert weak.rating < 800
        assert strong.rating - weak.rating > 400

    def test_multiple_games_accumulate(self):
        a = ModelRating(name="a")
        b = ModelRating(name="b")
        update_ratings(a, b, "b-1")
        update_ratings(a, b, "b-2")
        assert a.total_games == 2
        assert b.total_games == 2

class TestConfidenceInterval:
    """Tests for the rating confidence interval calculation."""

    def test_no_games_wide_interval(self):
        """No games played should give a very wide interval."""
        from evalarena.core.elo import rating_confidence_interval
        lo, hi = rating_confidence_interval(1000.0, 0)
        assert lo == 600.0
        assert hi == 1400.0

    def test_many_games_narrow_interval(self):
        """Many games should narrow the interval."""
        from evalarena.core.elo import rating_confidence_interval
        lo, hi = rating_confidence_interval(1200.0, 100)
        assert lo > 1100.0
        assert hi < 1300.0

    def test_interval_symmetric(self):
        """Interval should be symmetric around the rating."""
        from evalarena.core.elo import rating_confidence_interval
        rating = 1100.0
        lo, hi = rating_confidence_interval(rating, 50)
        assert (rating - lo) == pytest.approx(hi - rating, abs=0.1)

    def test_more_games_tighter(self):
        """More games should result in a tighter interval."""
        from evalarena.core.elo import rating_confidence_interval
        lo1, hi1 = rating_confidence_interval(1000.0, 10)
        lo2, hi2 = rating_confidence_interval(1000.0, 100)
        width1 = hi1 - lo1
        width2 = hi2 - lo2
        assert width2 < width1

    def test_custom_z_score(self):
        """Custom z-score should scale the interval."""
        from evalarena.core.elo import rating_confidence_interval
        lo95, hi95 = rating_confidence_interval(1000.0, 50, confidence=1.96)
        lo99, hi99 = rating_confidence_interval(1000.0, 50, confidence=2.576)
        assert (hi99 - lo99) > (hi95 - lo95)

    def test_zero_games_custom_rating(self):
        """Zero games with custom rating should still work."""
        from evalarena.core.elo import rating_confidence_interval
        lo, hi = rating_confidence_interval(1500.0, 0)
        assert lo == 1100.0
        assert hi == 1900.0

    def test_one_game(self):
        """One game should give the maximum possible interval width."""
        from evalarena.core.elo import rating_confidence_interval
        lo, hi = rating_confidence_interval(1000.0, 1)
        assert lo == 216.0  # 1000 - 1.96 * 400
        assert hi == 1784.0  # 1000 + 1.96 * 400
