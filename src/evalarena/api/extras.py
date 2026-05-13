"""API routes for batch battles and model trends."""

from fastapi import APIRouter, HTTPException, Query

from evalarena.db.database import Database
from evalarena.db.models import (
    BatchBattleCreate,
    BatchBattleOut,
    ModelTrendOut,
    ModelTrendPoint,
    BattleCreate,
)

router = APIRouter(tags=["arena", "models"])


def get_db() -> Database:
    """Get database instance -- overridden at app startup."""
    raise RuntimeError("Database not configured")


@router.post("/api/arena/batch", response_model=BatchBattleOut, status_code=201)
async def batch_create_battles(data: BatchBattleCreate) -> BatchBattleOut:
    """Create multiple battles from a list of prompts.

    Auto-samples responses from both models for each prompt. Supports
    batch evaluation of model pairs across multiple prompts.
    """
    import random
    from evalarena.providers import get_provider, ProviderError

    db = get_db()

    # Validate models
    model_a = await db.get_model(data.model_a_id)
    model_b = await db.get_model(data.model_b_id)
    if not model_a:
        raise HTTPException(status_code=404, detail=f"Model '{data.model_a_id}' not found")
    if not model_b:
        raise HTTPException(status_code=404, detail=f"Model '{data.model_b_id}' not found")
    if data.model_a_id == data.model_b_id:
        raise HTTPException(status_code=400, detail="Cannot battle a model against itself")

    # Validate providers
    provider_a = get_provider(model_a.provider)
    if not provider_a:
        raise HTTPException(
            status_code=400,
            detail=f"Provider '{model_a.provider}' not available for model '{model_a.name}'",
        )
    if not provider_a.is_configured():
        raise HTTPException(
            status_code=400,
            detail=f"Provider '{model_a.provider}' is not configured (missing API key?)",
        )

    provider_b = get_provider(model_b.provider)
    if not provider_b:
        raise HTTPException(
            status_code=400,
            detail=f"Provider '{model_b.provider}' not available for model '{model_b.name}'",
        )
    if not provider_b.is_configured():
        raise HTTPException(
            status_code=400,
            detail=f"Provider '{model_b.provider}' is not configured (missing API key?)",
        )

    # Create battles for each prompt
    battle_ids: list[str] = []
    errors: list[str] = []

    for i, prompt in enumerate(data.prompts):
        try:
            resp_a = await provider_a.generate(
                prompt,
                model_a.api_model_id or model_a.name,
                temperature=data.temperature,
                max_tokens=data.max_tokens,
            )
            resp_b = await provider_b.generate(
                prompt,
                model_b.api_model_id or model_b.name,
                temperature=data.temperature,
                max_tokens=data.max_tokens,
            )

            # Random swap to eliminate position bias
            battle_data = BattleCreate(
                prompt=prompt,
                response_a=resp_a.text,
                response_b=resp_b.text,
                model_a_id=data.model_a_id,
                model_b_id=data.model_b_id,
            )
            if random.random() < 0.5:
                battle_data.model_a_id, battle_data.model_b_id = battle_data.model_b_id, battle_data.model_a_id
                battle_data.response_a, battle_data.response_b = battle_data.response_b, battle_data.response_a

            battle = await db.create_battle(battle_data)
            battle_ids.append(battle.id)
        except ProviderError as e:
            errors.append(f"Prompt {i+1}: {e}")
        except Exception as e:
            errors.append(f"Prompt {i+1}: unexpected error: {e}")

    if not battle_ids:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to create any battles. Errors: {'; '.join(errors)}",
        )

    return BatchBattleOut(
        battles_created=len(battle_ids),
        battle_ids=battle_ids,
        model_a=model_a.name,
        model_b=model_b.name,
    )


@router.get("/api/models/{model_id}/trends", response_model=ModelTrendOut)
async def get_model_trends(
    model_id: str,
    limit: int = Query(100, ge=1, le=500, description="Max data points"),
) -> ModelTrendOut:
    """Get rating trend data for chart visualization.

    Returns chronological rating snapshots after each voted battle,
    suitable for plotting a model's rating over time.
    """
    db = get_db()
    model = await db.get_model(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    points = await db.get_model_trends(model_id, limit=limit)
    return ModelTrendOut(
        model_id=model_id,
        model_name=model.name,
        current_rating=model.rating,
        points=points,
    )


@router.get("/api/battles/with-comments")
async def get_battles_with_comments(
    limit: int = Query(30, ge=1, le=100, description="Max battles"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
) -> list[dict]:
    """Get voted battles with vote comments.

    Returns battles that have been voted on, including any comments
    left by voters explaining their reasoning.
    """
    db = get_db()
    return await db.get_battles_with_comments(limit=limit, offset=offset)
