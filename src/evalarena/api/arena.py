"""API routes for arena battles."""

import random

from fastapi import APIRouter, HTTPException

from evalarena.db.database import Database
from evalarena.db.models import BattleCreate, BattleOut, BattleDetail, AutoBattleCreate

router = APIRouter(prefix="/api/arena", tags=["arena"])


def get_db() -> Database:
    raise RuntimeError("Database not configured")


@router.post("", response_model=BattleOut, status_code=201)
async def create_battle(data: BattleCreate) -> BattleOut:
    """Create a new blind battle between two models.

    The caller provides prompt + responses. Model identities are hidden
    from voters -- only revealed after voting.
    """
    db = get_db()
    # Validate both models exist
    model_a = await db.get_model(data.model_a_id)
    model_b = await db.get_model(data.model_b_id)
    if not model_a:
        raise HTTPException(status_code=404, detail=f"Model \'{data.model_a_id}\' not found")
    if not model_b:
        raise HTTPException(status_code=404, detail=f"Model \'{data.model_b_id}\' not found")
    if data.model_a_id == data.model_b_id:
        raise HTTPException(status_code=400, detail="Cannot battle a model against itself")

    # Randomly swap A/B to eliminate position bias
    if random.random() < 0.5:
        data.model_a_id, data.model_b_id = data.model_b_id, data.model_a_id
        data.response_a, data.response_b = data.response_b, data.response_a

    return await db.create_battle(data)


@router.get("", response_model=list[BattleOut])
async def list_battles(
    limit: int = 20, offset: int = 0, unvoted_only: bool = False
) -> list[BattleOut]:
    """List recent battles (blind -- no model identities).

    Args:
        unvoted_only: If True, return only battles that haven\'t been voted on yet.
    """
    db = get_db()
    return await db.list_battles(limit=limit, offset=offset, unvoted_only=unvoted_only)


@router.get("/random/pair")
async def random_pair() -> dict:
    """Pick two random models for a battle (utility endpoint)."""
    db = get_db()
    models = await db.list_models()
    if len(models) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 models")
    pair = random.sample(models, 2)
    return {"model_a": pair[0].id, "model_b": pair[1].id}


@router.get("/{battle_id}", response_model=BattleDetail)
async def get_battle(battle_id: str) -> BattleDetail:
    """Get battle details. Reveals model identities only if already voted on."""
    db = get_db()
    battle = await db.get_battle(battle_id)
    if not battle:
        raise HTTPException(status_code=404, detail="Battle not found")

    model_a = await db.get_model(battle["model_a_id"])
    model_b = await db.get_model(battle["model_b_id"])

    return BattleDetail(
        id=battle["id"],
        prompt=battle["prompt"],
        response_a=battle["response_a"],
        response_b=battle["response_b"],
        model_a_name=model_a.name if model_a else "unknown",
        model_b_name=model_b.name if model_b else "unknown",
        winner=battle["winner"],
        created_at=battle["created_at"],
    )


@router.post("/auto-battle", response_model=BattleOut, status_code=201)
async def auto_battle(data: AutoBattleCreate) -> BattleOut:
    """Create a battle by auto-sampling responses from LLM providers.

    Both models must have a ``provider`` and ``api_model_id`` configured.
    The arena calls each model's LLM provider API to generate responses,
    then creates a blind battle for human evaluation.
    """
    from evalarena.providers import get_provider, ProviderError

    db = get_db()
    model_a = await db.get_model(data.model_a_id)
    model_b = await db.get_model(data.model_b_id)
    if not model_a:
        raise HTTPException(status_code=404, detail=f"Model '{data.model_a_id}' not found")
    if not model_b:
        raise HTTPException(status_code=404, detail=f"Model '{data.model_b_id}' not found")
    if data.model_a_id == data.model_b_id:
        raise HTTPException(status_code=400, detail="Cannot battle a model against itself")

    # Get provider for model A
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

    # Get provider for model B
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

    # Generate responses from both models
    try:
        resp_a = await provider_a.generate(
            data.prompt,
            model_a.api_model_id or model_a.name,
            temperature=data.temperature,
            max_tokens=data.max_tokens,
        )
    except ProviderError as e:
        raise HTTPException(status_code=502, detail=f"Failed to get response from '{model_a.name}': {e}")

    try:
        resp_b = await provider_b.generate(
            data.prompt,
            model_b.api_model_id or model_b.name,
            temperature=data.temperature,
            max_tokens=data.max_tokens,
        )
    except ProviderError as e:
        raise HTTPException(status_code=502, detail=f"Failed to get response from '{model_b.name}': {e}")

    # Randomly swap A/B to eliminate position bias
    battle_data = BattleCreate(
        prompt=data.prompt,
        response_a=resp_a.text,
        response_b=resp_b.text,
        model_a_id=data.model_a_id,
        model_b_id=data.model_b_id,
    )

    if random.random() < 0.5:
        battle_data.model_a_id, battle_data.model_b_id = battle_data.model_b_id, battle_data.model_a_id
        battle_data.response_a, battle_data.response_b = battle_data.response_b, battle_data.response_a

    return await db.create_battle(battle_data)
