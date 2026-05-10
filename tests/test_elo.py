"""Tests for ELO rating system."""
from evalarena.core.elo import expected_score, update_ratings, DEFAULT_K, DEFAULT_RATING


class TestExpectedScore:
    """Tests for expected_score calculation."""

    def test_equal_ratings(self):
        """Two equally rated players should each have expected score of 0.5."""
        assert expected_score(1000, 1000) == 0.5

    def test_higher_rated_advantage(self):
        """Higher rated player should have expected score > 0.5."""
        score = expected_score(1200, 1000)
        assert score > 0.5
        assert score < 1.0

    def test_lower_rated_disadvantage(self):
        """Lower rated player should have expected score < 0.5."""
        score = expected_score(1000, 1200)
        assert score < 0.5
        assert score > 0.0

    def test_large_rating_gap(self):
        """Large rating gap means near-certain outcome."""
        score = expected_score(1600, 1000)
        assert score > 0.96

    def test_symmetry(self):
        """Expected scores should sum to 1.0."""
        ea = expected_score(1100, 1300)
        eb = expected_score(1300, 1100)
        assert abs(ea + eb - 1.0) < 1e-10

    def test_200_point_gap(self):
        """200-point gap ~ 76% expected win rate."""
        score = expected_score(1200, 1000)
        assert abs(score - 0.76) < 0.01


class TestUpdateRatings:
    """Tests for update_ratings after a match."""

    def test_equal_ratings_higher_wins(self):
        """When equal-rated players play, winner gains K/2 and loser loses K/2."""
        new_a, new_b = update_ratings(1000, 1000, 1.0)
        assert new_a == 1000 + DEFAULT_K / 2  # 1016.0
        assert new_b == 1000 - DEFAULT_K / 2  # 984.0

    def test_equal_ratings_tie(self):
        """When equal-rated players tie, no change."""
        new_a, new_b = update_ratings(1000, 1000, 0.5)
        assert new_a == 1000.0
        assert new_b == 1000.0

    def test_upset_win_bigger_gain(self):
        """Lower-rated player beating higher-rated should gain more points."""
        new_a, new_b = update_ratings(1000, 1200, 1.0)
        gain = new_a - 1000
        # Upset win should gain more than K/2
        assert gain > DEFAULT_K / 2

    def test_expected_win_smaller_gain(self):
        """Higher-rated player beating lower-rated should gain fewer points."""
        new_a, new_b = update_ratings(1200, 1000, 1.0)
        gain = new_a - 1200
        # Expected win should gain less than K/2
        assert gain < DEFAULT_K / 2

    def test_rating_conservation(self):
        """Total rating points should be conserved."""
        initial_total = 1000 + 1200
        new_a, new_b = update_ratings(1000, 1200, 0.8)
        assert abs((new_a + new_b) - initial_total) < 0.1

    def test_custom_k_factor(self):
        """Custom K-factor should scale the rating change."""
        new_a_default, _ = update_ratings(1000, 1000, 1.0, k=DEFAULT_K)
        new_a_small, _ = update_ratings(1000, 1000, 1.0, k=16)
        gain_default = new_a_default - 1000
        gain_small = new_a_small - 1000
        assert gain_default == 2 * gain_small

    def test_b_wins(self):
        """When B wins, B gains and A loses."""
        new_a, new_b = update_ratings(1000, 1000, 0.0)
        assert new_a < 1000
        assert new_b > 1000

    def test_zero_k_no_change(self):
        """K=0 means no rating change."""
        new_a, new_b = update_ratings(1000, 1200, 1.0, k=0)
        assert new_a == 1000.0
        assert new_b == 1200.0
