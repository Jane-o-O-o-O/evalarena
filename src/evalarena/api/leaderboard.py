"""API routes for leaderboard."""

from fastapi import APIRouter

from evalarena.db.database import Database
from evalarena.db.models import LeaderboardEntry, LeaderboardOut

router = APIRouter(prefix="/api/leaderboard", tags=["leaderboard"])


def get_db() -> Database:
    raise RuntimeError("Database not configured")


@router.get("", response_model=LeaderboardOut)
async def get_leaderboard(limit: int = 50, offset: int = 0) -> LeaderboardOut:
    """Get the model leaderboard ranked by ELO rating."""
    db = get_db()
    entries = await db.get_leaderboard(limit=limit, offset=offset)
    total = await db.count_models()
    return LeaderboardOut(entries=entries, total_models=total)
