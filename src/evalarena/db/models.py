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
    description: str = Field(
        default="",
        max_length=2000,
        description="Model description or notes",
    )
    organization: str = Field(
        default="",
        max_length=200,
        description="Organization or author that created the model",
    )
    parameter_count: str = Field(
        default="",
        max_length=50,
        description="Parameter count, e.g. '7B', '70B', '1.5T'",
    )
    provider: str = Field(
        default="",
        max_length=50,
        description="LLM provider name for auto-sampling (e.g. 'openai', 'anthropic')",
    )
    api_model_id: str = Field(
        default="",
        max_length=200,
        description="Model identifier for the LLM provider API (e.g. 'gpt-4o')",
    )


class ModelUpdate(BaseModel):
    """Request to update an existing model's metadata.

    All fields are optional -- only provided fields are updated.
    """

    name: str | None = Field(None, min_length=1, max_length=200)
    category: str | None = Field(None, min_length=1, max_length=50)
    description: str | None = Field(None, max_length=2000)
    organization: str | None = Field(None, max_length=200)
    parameter_count: str | None = Field(None, max_length=50)
    provider: str | None = Field(None, max_length=50)
    api_model_id: str | None = Field(None, max_length=200)


class ModelOut(BaseModel):
    """Model returned from API."""

    id: str
    name: str
    category: str = "general"
    description: str = ""
    organization: str = ""
    parameter_count: str = ""
    provider: str = ""
    api_model_id: str = ""
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
    description: str = ""
    organization: str = ""
    parameter_count: str = ""
    provider: str = ""
    api_model_id: str = ""
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


class AutoBattleCreate(BaseModel):
    """Request to create a battle by auto-sampling LLM responses.

    Instead of providing pre-generated responses, the arena calls LLM provider
    APIs to generate responses from both models for the given prompt.
    """

    prompt: str = Field(..., min_length=1, max_length=10000, examples=["Explain recursion."])
    model_a_id: str = Field(..., min_length=1)
    model_b_id: str = Field(..., min_length=1)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=1, le=32000)


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


class RatingHistoryEntry(BaseModel):
    """A single rating snapshot for a model after a battle."""

    battle_id: str
    rating: float
    rating_change: float
    opponent_name: str
    result: str  # "win", "loss", "tie"
    created_at: str


# Resolve forward references
ModelDetail.model_rebuild()
