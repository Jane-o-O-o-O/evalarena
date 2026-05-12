"""API routes for leaderboard."""

from fastapi import APIRouter, Query

from evalarena.db.database import Database
from evalarena.db.models import LeaderboardEntry, LeaderboardOut

router = APIRouter(prefix="/api/leaderboard", tags=["leaderboard"])


def get_db() -> Database:
    raise RuntimeError("Database not configured")


@router.get("", response_model=LeaderboardOut)
async def get_leaderboard(
    limit: int = 50,
    offset: int = 0,
    category: str | None = Query(None, description="Filter by category"),
) -> LeaderboardOut:
    """Get the model leaderboard ranked by ELO rating.

    Optionally filter by category to get category-specific rankings.
    """
    db = get_db()
    entries = await db.get_leaderboard(limit=limit, offset=offset, category=category)
    total = await db.count_models()
    return LeaderboardOut(entries=entries, total_models=total)


@router.get("/categories")
async def list_categories() -> dict:
    """List all available model categories."""
    db = get_db()
    categories = await db.list_categories()
    return {"categories": categories}
