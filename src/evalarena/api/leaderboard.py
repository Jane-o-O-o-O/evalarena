"""Leaderboard API endpoints."""
from fastapi import APIRouter, Query

from evalarena.core.models import list_models

router = APIRouter(prefix="/api/leaderboard", tags=["leaderboard"])


@router.get("")
async def get_leaderboard(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    min_games: int = Query(0, ge=0),
):
    """Get the leaderboard sorted by ELO rating."""
    models = await list_models(order_by="elo_rating", descending=True)
    # Filter by min games
    if min_games > 0:
        models = [m for m in models if m.games_played >= min_games]
    total = len(models)
    models = models[offset : offset + limit]
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "models": [m.to_dict() for m in models],
    }
