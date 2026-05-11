"""Pydantic data models for API request/response validation."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Winner(str, Enum):
    """Possible battle outcomes."""

    MODEL_A = "model_a"
    MODEL_B = "model_b"
    TIE = "tie"


# ── Model ────────────────────────────────────────────────────────────


class ModelCreate(BaseModel):
    """Request to register a new model."""

    name: str = Field(..., min_length=1, max_length=200, examples=["gpt-4o"])


class ModelOut(BaseModel):
    """Model returned from API."""

    id: str
    name: str
    rating: float
    wins: int
    losses: int
    ties: int
    total_games: int
    win_rate: float


# ── Battle ───────────────────────────────────────────────────────────


class BattleCreate(BaseModel):
    """Request to create a new battle."""

    prompt: str = Field(..., min_length=1, max_length=10000, examples=["Explain recursion."])
    response_a: str = Field(..., min_length=1, max_length=50000)
    response_b: str = Field(..., min_length=1, max_length=50000)
    model_a_id: str = Field(..., min_length=1)
    model_b_id: str = Field(..., min_length=1)


class BattleOut(BaseModel):
    """Battle returned from API (blind — no model identities)."""

    id: str
    prompt: str
    response_a: str
    response_b: str
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


# ── Vote ─────────────────────────────────────────────────────────────


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


# ── Leaderboard ──────────────────────────────────────────────────────


class LeaderboardEntry(BaseModel):
    """A single entry in the leaderboard."""

    rank: int
    model_id: str
    name: str
    rating: float
    wins: int
    losses: int
    ties: int
    total_games: int
    win_rate: float


class LeaderboardOut(BaseModel):
    """Leaderboard response."""

    entries: list[LeaderboardEntry]
    total_models: int
