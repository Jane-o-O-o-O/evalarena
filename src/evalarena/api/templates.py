"""API routes for prompt templates."""

from fastapi import APIRouter, HTTPException, Query

from evalarena.db.database import Database
from evalarena.db.models import PromptTemplateCreate, PromptTemplateOut, PromptTemplateUpdate

router = APIRouter(prefix="/api/templates", tags=["templates"])


def get_db() -> Database:
    """Get database instance -- overridden at app startup."""
    raise RuntimeError("Database not configured")


@router.post("", response_model=PromptTemplateOut, status_code=201)
async def create_template(data: PromptTemplateCreate) -> PromptTemplateOut:
    """Create a new prompt template."""
    db = get_db()
    existing = await db.get_prompt_template_by_name(data.name)
    if existing:
        raise HTTPException(status_code=409, detail=f"Template '{data.name}' already exists")
    return await db.create_prompt_template(data)


@router.get("", response_model=list[PromptTemplateOut])
async def list_templates(
    category: str | None = Query(None, description="Filter by category"),
) -> list[PromptTemplateOut]:
    """List all prompt templates, optionally filtered by category."""
    db = get_db()
    return await db.list_prompt_templates(category=category)


@router.get("/categories")
async def list_template_categories() -> list[str]:
    """List all distinct prompt template categories."""
    db = get_db()
    return await db.list_template_categories()


@router.get("/{template_id}", response_model=PromptTemplateOut)
async def get_template(template_id: str) -> PromptTemplateOut:
    """Get a specific prompt template by ID."""
    db = get_db()
    template = await db.get_prompt_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@router.put("/{template_id}", response_model=PromptTemplateOut)
async def update_template(template_id: str, data: PromptTemplateUpdate) -> PromptTemplateOut:
    """Update a prompt template's metadata."""
    db = get_db()
    if data.name:
        existing = await db.get_prompt_template_by_name(data.name)
        if existing and existing.id != template_id:
            raise HTTPException(status_code=409, detail=f"Template '{data.name}' already exists")
    updated = await db.update_prompt_template(template_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="Template not found")
    return updated


@router.delete("/{template_id}", status_code=204)
async def delete_template(template_id: str) -> None:
    """Delete a prompt template."""
    db = get_db()
    if not await db.delete_prompt_template(template_id):
        raise HTTPException(status_code=404, detail="Template not found")


@router.get("/{template_id}/random-battle")
async def template_random_battle(template_id: str) -> dict:
    """Create a random battle using this template's prompt.

    Picks two random models and creates a blind battle with the template's prompt.
    Returns the battle data for voting.
    """
    import random

    db = get_db()
    template = await db.get_prompt_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    models = await db.list_models()
    if len(models) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 models")

    pair = random.sample(models, 2)

    # Increment template usage
    await db.increment_template_usage(template_id)

    return {
        "template_id": template.id,
        "prompt": template.prompt_text,
        "model_a": pair[0].id,
        "model_b": pair[1].id,
        "model_a_name": pair[0].name,
        "model_b_name": pair[1].name,
    }
