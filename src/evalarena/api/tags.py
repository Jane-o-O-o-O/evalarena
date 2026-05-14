"""API routes for model tags management.

Tags provide flexible multi-label categorization for models,
complementing the single-category field with rich metadata.
"""

from fastapi import APIRouter, HTTPException, Query

from evalarena.db.database import Database
from evalarena.db.models import TagCreate, TagOut, TagUpdate

router = APIRouter(prefix="/api/tags", tags=["tags"])


def get_db() -> Database:
    """Get database instance -- overridden at app startup."""
    raise RuntimeError("Database not configured")


@router.post("", response_model=TagOut, status_code=201)
async def create_tag(data: TagCreate) -> TagOut:
    """Create a new tag for categorizing models.

    Tags are a flexible labeling system — a model can have multiple tags
    (e.g. 'open-source', 'fine-tuned', 'reasoning-strong') in addition
    to its primary category.
    """
    db = get_db()
    existing = await db.get_tag_by_name(data.name)
    if existing:
        raise HTTPException(status_code=409, detail=f"Tag '{data.name}' already exists")
    result = await db.create_tag(data.name, data.color)
    return TagOut(**result)


@router.get("", response_model=list[TagOut])
async def list_tags() -> list[TagOut]:
    """List all tags with their model counts."""
    db = get_db()
    tags = await db.list_tags()
    return [TagOut(**t) for t in tags]


@router.get("/{tag_id}", response_model=TagOut)
async def get_tag(tag_id: str) -> TagOut:
    """Get a tag by ID."""
    db = get_db()
    tag = await db.get_tag(tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    return TagOut(**tag)


@router.put("/{tag_id}", response_model=TagOut)
async def update_tag(tag_id: str, data: TagUpdate) -> TagOut:
    """Update a tag's name or color."""
    db = get_db()
    result = await db.update_tag(tag_id, name=data.name, color=data.color)
    if not result:
        raise HTTPException(status_code=404, detail="Tag not found")
    return TagOut(**result)


@router.delete("/{tag_id}")
async def delete_tag(tag_id: str) -> dict:
    """Delete a tag and remove all model associations."""
    db = get_db()
    deleted = await db.delete_tag(tag_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Tag not found")
    return {"detail": "Tag deleted"}


@router.post("/{tag_id}/models/{model_id}")
async def add_tag_to_model(tag_id: str, model_id: str) -> dict:
    """Associate a tag with a model."""
    db = get_db()
    try:
        await db.add_model_tag(model_id, tag_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"detail": "Tag associated with model"}


@router.delete("/{tag_id}/models/{model_id}")
async def remove_tag_from_model(tag_id: str, model_id: str) -> dict:
    """Remove a tag from a model."""
    db = get_db()
    await db.remove_model_tag(model_id, tag_id)
    return {"detail": "Tag removed from model"}


@router.get("/{tag_id}/models")
async def list_models_by_tag(tag_id: str) -> list[dict]:
    """List all models that have this tag."""
    db = get_db()
    tag = await db.get_tag(tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    models = await db.get_models_by_tag(tag_id)
    return [m.model_dump() for m in models]
