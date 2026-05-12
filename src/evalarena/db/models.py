"""Pydantic data models for API request/response validation."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Winner(str, Enum):
    """Possible battle outcomes."""

    MODEL_A = "model_a"
    MODEL_B = "model_b"
    TIE = "tie"


# -- Model ---------------------------------------------------------------


class ModelCreate(BaseModel):
    """Request to register a new model."""

    name: str = Field(..., min_length=1, max_length=200, examples=["gpt-4o"])
    category: str = Field(
        default="general",
        min_length=1,
        max_length=50,
        examples=["coding", "writing", "reasoning"],
        description="Evaluation category for grouped leaderboards",
    )


class ModelOut(BaseModel):
    """Model returned from API."""

    id: str
    name: str
    category: str = "general"
    rating: float
    wins: int
    losses: int
    ties: int
    total_games: int
    win_rate: float
    ci_lower: float = 0.0
    ci_upper: float = 0.0


class ModelDetail(BaseModel):
    """Extended model info with match history."""

    id: str
    name: str
    category: str = "general"
    rating: float
    wins: int
    losses: int
    ties: int
    total_games: int
    win_rate: float
    ci_lower: float
    ci_upper: float
    recent_battles: list["BattleSummary"] = []
    created_at: str = ""


class BattleSummary(BaseModel):
    """Brief battle info for match history."""

    id: str
    prompt: str
    opponent_name: str
    result: str  # "win", "loss", "tie"
    rating_change: float
    created_at: str


# -- Battle ---------------------------------------------------------------


class BattleCreate(BaseModel):
    """Request to create a new battle."""

    prompt: str = Field(..., min_length=1, max_length=10000, examples=["Explain recursion."])
    response_a: str = Field(..., min_length=1, max_length=50000)
    response_b: str = Field(..., min_length=1, max_length=50000)
    model_a_id: str = Field(..., min_length=1)
    model_b_id: str = Field(..., min_length=1)


class BattleOut(BaseModel):
    """Battle returned from API (blind -- no model identities)."""

    id: str
    prompt: str
    response_a: str
    response_b: str
    voted: bool = False
    created_at: str


class BattleDetail(BaseModel):
    """Battle with model identities revealed (after voting)."""

    id: str
    prompt: str
    response_a: str
    response_b: str
    model_a_name: str
    model_b_name: str
    winner: str | None = None
    created_at: str


# -- Vote ----------------------------------------------------------------


class VoteCreate(BaseModel):
    """Request to submit a vote."""

    battle_id: str = Field(..., min_length=1)
    winner: Winner


class VoteOut(BaseModel):
    """Vote returned from API."""

    id: str
    battle_id: str
    winner: str
    created_at: str


# -- Leaderboard ----------------------------------------------------------


class LeaderboardEntry(BaseModel):
    """A single entry in the leaderboard."""

    rank: int
    model_id: str
    name: str
    category: str = "general"
    rating: float
    wins: int
    losses: int
    ties: int
    total_games: int
    win_rate: float
    ci_lower: float = 0.0
    ci_upper: float = 0.0


class LeaderboardOut(BaseModel):
    """Leaderboard response."""

    entries: list[LeaderboardEntry]
    total_models: int


# -- Head-to-Head ---------------------------------------------------------


class HeadToHead(BaseModel):
    """Head-to-head comparison between two models."""

    model_a: str
    model_b: str
    model_a_wins: int
    model_b_wins: int
    ties: int
    total_battles: int
    model_a_win_rate: float
    model_a_rating_before: float = 0.0
    model_a_rating_after: float = 0.0
    model_b_rating_before: float = 0.0
    model_b_rating_after: float = 0.0


# -- Stats ----------------------------------------------------------------


class StatsOut(BaseModel):
    """Aggregate platform statistics."""

    total_models: int
    total_battles: int
    total_votes: int
    avg_rating: float
    highest_rating: float
    lowest_rating: float
    most_active_model: str = ""
    battles_today: int = 0


# Resolve forward references
ModelDetail.model_rebuild()
