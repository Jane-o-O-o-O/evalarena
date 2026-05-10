"""Model management API endpoints."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from evalarena.core.models import (
    register_model,
    get_model,
    get_model_by_name,
    list_models,
    delete_model,
)

router = APIRouter(prefix="/api/models", tags=["models"])


class ModelCreateRequest(BaseModel):
    """Request body for registering a model."""
    name: str = Field(..., min_length=1, max_length=100)
    organization: str | None = Field(None, max_length=200)
    description: str | None = Field(None, max_length=1000)
    initial_elo: float = Field(1000.0, ge=0, le=5000)


class ModelResponse(BaseModel):
    """Response body for a model."""
    id: int
    name: str
    organization: str | None
    description: str | None
    elo_rating: float
    games_played: int
    wins: int
    losses: int
    ties: int
    win_rate: float
    created_at: str
    updated_at: str


@router.post("", response_model=ModelResponse, status_code=201)
async def create_model(req: ModelCreateRequest):
    """Register a new model."""
    existing = await get_model_by_name(req.name)
    if existing:
        raise HTTPException(status_code=409, detail=f"Model '{req.name}' already exists")
    model = await register_model(
        name=req.name,
        organization=req.organization,
        description=req.description,
        initial_elo=req.initial_elo,
    )
    return model.to_dict()


@router.get("", response_model=list[ModelResponse])
async def list_all_models(
    order_by: str = "elo_rating",
    descending: bool = True,
):
    """List all registered models."""
    models = await list_models(order_by=order_by, descending=descending)
    return [m.to_dict() for m in models]


@router.get("/{model_id}", response_model=ModelResponse)
async def get_single_model(model_id: int):
    """Get a model by ID."""
    model = await get_model(model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="Model not found")
    return model.to_dict()


@router.delete("/{model_id}", status_code=204)
async def remove_model(model_id: int):
    """Delete a model."""
    deleted = await delete_model(model_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Model not found")
