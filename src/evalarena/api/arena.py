"""API routes for arena battles."""

import random

from fastapi import APIRouter, HTTPException

from evalarena.db.database import Database
from evalarena.db.models import BattleCreate, BattleOut, BattleDetail

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
