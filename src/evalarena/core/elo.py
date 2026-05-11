"""ELO rating system for LLM model evaluation.

Implements the standard Elo rating algorithm with configurable K-factor,
supporting win/loss/tie outcomes. Based on the LMSYS Chatbot Arena approach.
"""

import math
from dataclasses import dataclass, field


@dataclass
class EloResult:
    """Result of an ELO rating update."""

    winner_new_rating: float
    loser_new_rating: float
    expected_winner: float
    expected_loser: float


@dataclass
class ModelRating:
    """Track a model's ELO rating and game history."""

    name: str
    rating: float = 1000.0
    wins: int = 0
    losses: int = 0
    ties: int = 0
    battle_ids: list[str] = field(default_factory=list)

    @property
    def total_games(self) -> int:
        """Total number of games played."""
        return self.wins + self.losses + self.ties

    @property
    def win_rate(self) -> float:
        """Win rate as a percentage."""
        if self.total_games == 0:
            return 0.0
        return self.wins / self.total_games * 100


def expected_score(rating_a: float, rating_b: float) -> float:
    """Calculate expected score for player A against player B.

    Args:
        rating_a: Rating of player A.
        rating_b: Rating of player B.

    Returns:
        Expected score for A (0.0 to 1.0).
    """
    return 1.0 / (1.0 + math.pow(10, (rating_b - rating_a) / 400.0))


def calculate_elo_update(
    winner_rating: float,
    loser_rating: float,
    k_factor: float = 32.0,
    is_tie: bool = False,
) -> EloResult:
    """Calculate new ELO ratings after a match.

    Args:
        winner_rating: Current rating of the winner (or model_a in a tie).
        loser_rating: Current rating of the loser (or model_b in a tie).
        k_factor: K-factor controlling rating volatility. Default 32.
        is_tie: If True, treat as a draw (both players get 0.5 score).

    Returns:
        EloResult with new ratings and expected scores.
    """
    expected_win = expected_score(winner_rating, loser_rating)
    expected_lose = 1.0 - expected_win

    if is_tie:
        actual_winner = 0.5
        actual_loser = 0.5
    else:
        actual_winner = 1.0
        actual_loser = 0.0

    new_winner = winner_rating + k_factor * (actual_winner - expected_win)
    new_loser = loser_rating + k_factor * (actual_loser - expected_lose)

    return EloResult(
        winner_new_rating=round(new_winner, 1),
        loser_new_rating=round(new_loser, 1),
        expected_winner=round(expected_win, 4),
        expected_loser=round(expected_lose, 4),
    )


def update_ratings(
    winner: ModelRating,
    loser: ModelRating,
    battle_id: str,
    k_factor: float = 32.0,
    is_tie: bool = False,
) -> None:
    """Update two ModelRating objects in-place after a match.

    Args:
        winner: The winning model's rating object (or model_a in a tie).
        loser: The losing model's rating object (or model_b in a tie).
        battle_id: The battle identifier.
        k_factor: K-factor for rating calculation.
        is_tie: If True, treat as a draw.
    """
    result = calculate_elo_update(winner.rating, loser.rating, k_factor, is_tie)
    winner.rating = result.winner_new_rating
    loser.rating = result.loser_new_rating

    if is_tie:
        winner.ties += 1
        loser.ties += 1
    else:
        winner.wins += 1
        loser.losses += 1

    winner.battle_ids.append(battle_id)
    loser.battle_ids.append(battle_id)
