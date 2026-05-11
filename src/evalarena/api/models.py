"""API routes for model management."""

from fastapi import APIRouter, HTTPException

from evalarena.db.database import Database
from evalarena.db.models import HeadToHead, ModelCreate, ModelDetail, ModelOut

router = APIRouter(prefix="/api/models", tags=["models"])


def get_db() -> Database:
    """Get database instance -- overridden at app startup."""
    raise RuntimeError("Database not configured")


@router.post("", response_model=ModelOut, status_code=201)
async def create_model(data: ModelCreate) -> ModelOut:
    """Register a new model for evaluation."""
    db = get_db()
    existing = await db.get_model_by_name(data.name)
    if existing:
        raise HTTPException(status_code=409, detail=f"Model \'{data.name}\' already exists")
    return await db.create_model(data)


@router.get("", response_model=list[ModelOut])
async def list_models() -> list[ModelOut]:
    """List all registered models."""
    db = get_db()
    return await db.list_models()


@router.get("/{model_id}", response_model=ModelOut)
async def get_model(model_id: str) -> ModelOut:
    """Get a specific model by ID."""
    db = get_db()
    model = await db.get_model(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return model


@router.get("/{model_id}/detail", response_model=ModelDetail)
async def get_model_detail(model_id: str) -> ModelDetail:
    """Get detailed model info with match history."""
    db = get_db()
    detail = await db.get_model_detail(model_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Model not found")
    return detail


@router.get("/{model_id}/head-to-head/{other_id}", response_model=HeadToHead)
async def head_to_head(model_id: str, other_id: str) -> HeadToHead:
    """Get head-to-head comparison between two models."""
    db = get_db()
    try:
        return await db.head_to_head(model_id, other_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{model_id}", status_code=204)
async def delete_model(model_id: str) -> None:
    """Remove a model."""
    db = get_db()
    if not await db.delete_model(model_id):
        raise HTTPException(status_code=404, detail="Model not found")
