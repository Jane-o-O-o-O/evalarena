"""ELO rating system implementation.

Standard ELO formula with configurable K-factor.
Rating = R_old + K * (actual_score - expected_score)
Expected score = 1 / (1 + 10^((R_opponent - R_self) / 400))
"""
import math

DEFAULT_K = 32.0
DEFAULT_RATING = 1000.0


def expected_score(rating_a: float, rating_b: float) -> float:
    """Calculate expected score for player A against player B."""
    return 1.0 / (1.0 + math.pow(10, (rating_b - rating_a) / 400.0))


def update_ratings(
    rating_a: float,
    rating_b: float,
    result: float,  # 1.0 = A wins, 0.0 = B wins, 0.5 = tie
    k: float = DEFAULT_K,
) -> tuple[float, float]:
    """Update ratings after a match.

    Args:
        rating_a: Current rating of player A.
        rating_b: Current rating of player B.
        result: Match result (1.0=A wins, 0.0=B wins, 0.5=tie).
        k: K-factor (maximum change per game).

    Returns:
        Tuple of (new_rating_a, new_rating_b).
    """
    expected_a = expected_score(rating_a, rating_b)
    expected_b = 1.0 - expected_a

    new_rating_a = rating_a + k * (result - expected_a)
    new_rating_b = rating_b + k * ((1.0 - result) - expected_b)

    return round(new_rating_a, 1), round(new_rating_b, 1)
