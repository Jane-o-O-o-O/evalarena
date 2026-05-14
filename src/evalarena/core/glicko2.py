"""Glicko-2 rating system for LLM model evaluation.

An improvement over the standard Elo system that tracks three parameters:
- Rating (μ): the model's skill estimate
- Rating Deviation (RD, φ): uncertainty in the rating
- Volatility (σ): how consistent the model's performance is

Glicko-2 is particularly better than Elo when:
- Models have very different numbers of games
- Models are new (high RD means rapid rating adjustment)
- We want confidence intervals that are statistically meaningful

Based on Mark Glickman's Glicko-2 algorithm:
http://www.glickman.net/glicko/glicko2.pdf
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


# Glicko-2 uses a different scale than Elo. Standard mapping:
# Glicko-2 rating = (Elo rating - 1500) / 173.7178
G_SCALE = 173.7178
GLICKO2_DEFAULT_RATING = 1500.0
GLICKO2_DEFAULT_RD = 350.0
GLICKO2_DEFAULT_VOLATILITY = 0.06
TAU = 0.5  # System constant, constrains volatility change
EPSILON = 0.000001  # Convergence tolerance


@dataclass
class Glicko2Player:
    """Track a model's Glicko-2 rating parameters.

    Attributes:
        name: Model name identifier.
        rating: Rating in Glicko-2 scale (default 1500, like Elo scale).
        rd: Rating deviation in Glicko-2 scale (default 350).
        volatility: Performance volatility (default 0.06).
        wins: Total wins.
        losses: Total losses.
        ties: Total ties.
        battle_ids: List of battle IDs played.
    """

    name: str
    rating: float = GLICKO2_DEFAULT_RATING
    rd: float = GLICKO2_DEFAULT_RD
    volatility: float = GLICKO2_DEFAULT_VOLATILITY
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

    @property
    def confidence_interval(self) -> tuple[float, float]:
        """95% confidence interval for rating in Elo-like scale.

        Uses RD as the standard deviation: CI = rating ± 1.96 * rd.
        This is more statistically meaningful than the Elo CI heuristic.
        """
        margin = 1.96 * self.rd
        return (round(self.rating - margin, 1), round(self.rating + margin, 1))

    def _to_glicko2_scale(self) -> float:
        """Convert rating to Glicko-2 internal scale (μ)."""
        return (self.rating - GLICKO2_DEFAULT_RATING) / G_SCALE

    def _rd_to_glicko2_scale(self) -> float:
        """Convert RD to Glicko-2 internal scale (φ)."""
        return self.rd / G_SCALE

    @staticmethod
    def _from_glicko2_scale(mu: float) -> float:
        """Convert from Glicko-2 internal scale back to rating."""
        return mu * G_SCALE + GLICKO2_DEFAULT_RATING

    @staticmethod
    def _rd_from_glicko2_scale(phi: float) -> float:
        """Convert from Glicko-2 internal scale back to RD."""
        return phi * G_SCALE


def _g(phi: float) -> float:
    """Glicko-2 g function: scaling of RD.

    Args:
        phi: Opponent's rating deviation in Glicko-2 scale.

    Returns:
        Scaling factor for the opponent's rating.
    """
    return 1.0 / math.sqrt(1.0 + 3.0 * phi * phi / (math.pi * math.pi))


def _E(mu: float, mu_j: float, phi_j: float) -> float:
    """Expected score of player against opponent j.

    Args:
        mu: Player's rating in Glicko-2 scale.
        mu_j: Opponent's rating in Glicko-2 scale.
        phi_j: Opponent's RD in Glicko-2 scale.

    Returns:
        Expected score (0.0 to 1.0).
    """
    return 1.0 / (1.0 + math.exp(-_g(phi_j) * (mu - mu_j)))


def _v(mu: float, opponents: list[tuple[float, float, float]]) -> float:
    """Estimated variance of the player's rating.

    Args:
        mu: Player's rating in Glicko-2 scale.
        opponents: List of (mu_j, phi_j, score_j) tuples.

    Returns:
        Estimated variance (inverse of information amount).
    """
    total = 0.0
    for mu_j, phi_j, _ in opponents:
        g_val = _g(phi_j)
        e_val = _E(mu, mu_j, phi_j)
        total += g_val * g_val * e_val * (1.0 - e_val)
    if total == 0:
        return float('inf')
    return 1.0 / total


def _delta(
    mu: float,
    v_inv: float,
    opponents: list[tuple[float, float, float]],
) -> float:
    """Estimated improvement in rating (Δ).

    Args:
        mu: Player's rating in Glicko-2 scale.
        v_inv: The estimated variance (v, NOT 1/v).
        opponents: List of (mu_j, phi_j, score_j) tuples.

    Returns:
        Estimated improvement delta.
    """
    total = 0.0
    for mu_j, phi_j, score_j in opponents:
        g_val = _g(phi_j)
        e_val = _E(mu, mu_j, phi_j)
        total += g_val * (score_j - e_val)
    return v_inv * total


def _new_volatility(
    phi: float,
    v: float,
    delta: float,
    sigma: float,
) -> float:
    """Compute new volatility σ' using the Illinois algorithm.

    This is a simplified but accurate implementation of step 5.2.2
    from the Glicko-2 paper.

    Args:
        phi: Current RD in Glicko-2 scale.
        v: Estimated variance.
        delta: Estimated improvement.
        sigma: Current volatility.

    Returns:
        New volatility value.
    """
    a = math.log(sigma * sigma)

    def f(x: float) -> float:
        ex = math.exp(x)
        phi2 = phi * phi + v + ex
        d2 = delta * delta
        return (ex * (d2 - phi2 - ex)) / (2.0 * phi2 * phi2) - (x - a) / (TAU * TAU)

    # Find bracket [A, B]
    if delta * delta > phi * phi + v:
        B = math.log(delta * delta - phi * phi - v)
    else:
        k = 1
        while f(a - k * TAU) < 0:
            k += 1
        B = a - k * TAU

    A = a
    fA = f(A)
    fB = f(B)

    # Illinois algorithm iteration
    for _ in range(100):
        C = A + (A - B) * fA / (fB - fA)
        fC = f(C)

        if abs(fC) < EPSILON or abs(B - A) < EPSILON:
            break

        if fC * fB < 0:
            A = B
            fA = fB
        else:
            fA /= 2.0

        B = C
        fB = fC

    return math.exp(A / 2.0)


def update_glicko2(
    player: Glicko2Player,
    opponents: list[Glicko2Player],
    scores: list[float],
) -> None:
    """Update a player's Glicko-2 rating after a rating period.

    This implements the full Glicko-2 algorithm for one rating period.

    Args:
        player: The player to update.
        opponents: List of opponents faced in this period.
        scores: List of scores against each opponent (1.0=win, 0.5=tie, 0.0=loss).

    Raises:
        ValueError: If opponents and scores have different lengths.
    """
    if len(opponents) != len(scores):
        raise ValueError("opponents and scores must have the same length")

    if len(opponents) == 0:
        # No games: just increase RD (rating becomes less certain over time)
        phi = player._rd_to_glicko2_scale()
        sigma = player.volatility
        phi_new = math.sqrt(phi * phi + sigma * sigma)
        player.rd = Glicko2Player._rd_from_glicko2_scale(phi_new)
        return

    # Step 1-2: Convert to Glicko-2 scale
    mu = player._to_glicko2_scale()
    phi = player._rd_to_glicko2_scale()
    sigma = player.volatility

    # Step 3: Compute estimated variance and delta
    opponent_data: list[tuple[float, float, float]] = []
    for opp, score in zip(opponents, scores):
        mu_j = opp._to_glicko2_scale()
        phi_j = opp._rd_to_glicko2_scale()
        opponent_data.append((mu_j, phi_j, score))

    v_val = _v(mu, opponent_data)
    delta_val = _delta(mu, v_val, opponent_data)

    # Step 4: Determine new volatility
    sigma_new = _new_volatility(phi, v_val, delta_val, sigma)

    # Step 5: Update RD
    phi_star = math.sqrt(phi * phi + sigma_new * sigma_new)

    # Step 6: Update RD and rating
    phi_new = 1.0 / math.sqrt(1.0 / (phi_star * phi_star) + 1.0 / v_val)
    mu_new = mu + phi_new * phi_new * sum(
        _g(phi_j) * (score_j - _E(mu, mu_j, phi_j))
        for mu_j, phi_j, score_j in opponent_data
    )

    # Convert back to standard scale
    player.rating = round(Glicko2Player._from_glicko2_scale(mu_new), 1)
    player.rd = round(Glicko2Player._rd_from_glicko2_scale(phi_new), 1)
    player.volatility = round(sigma_new, 6)

    # Update win/loss/tie counts
    for opp, score in zip(opponents, scores):
        if score == 1.0:
            player.wins += 1
        elif score == 0.0:
            player.losses += 1
        else:
            player.ties += 1


def glicko2_win_probability(
    player_a: Glicko2Player,
    player_b: Glicko2Player,
) -> float:
    """Estimate win probability for player A against player B.

    Uses the Glicko-2 expected score formula, accounting for both
    rating and rating deviation.

    Args:
        player_a: First player.
        player_b: Second player.

    Returns:
        Estimated probability that A wins (0.0 to 1.0).
    """
    mu_a = player_a._to_glicko2_scale()
    mu_b = player_b._to_glicko2_scale()
    phi_b = player_b._rd_to_glicko2_scale()
    return round(_E(mu_a, mu_b, phi_b), 4)


def glicko2_from_elo(
    elo_rating: float,
    elo_games: int = 0,
) -> Glicko2Player:
    """Create a Glicko-2 player from existing Elo data.

    Approximates RD based on number of games played.
    More games = lower RD = more confidence in rating.

    Args:
        elo_rating: The Elo rating.
        elo_games: Number of games played (used to estimate RD).

    Returns:
        A new Glicko2Player initialized from Elo data.
    """
    # RD approximation: starts at 350, decreases with games
    # Roughly: RD ≈ 350 / sqrt(1 + games/10)
    if elo_games > 0:
        rd = min(350.0, 350.0 / math.sqrt(1.0 + elo_games / 10.0))
    else:
        rd = GLICKO2_DEFAULT_RD

    return Glicko2Player(
        name="elo-converted",
        rating=elo_rating,
        rd=round(rd, 1),
        volatility=GLICKO2_DEFAULT_VOLATILITY,
    )
