"""API routes for platform statistics."""

from fastapi import APIRouter

from evalarena.db.database import Database
from evalarena.db.models import StatsOut

router = APIRouter(prefix="/api/stats", tags=["stats"])


def get_db() -> Database:
    raise RuntimeError("Database not configured")


@router.get("", response_model=StatsOut)
async def get_stats() -> StatsOut:
    """Get aggregate platform statistics.

    Returns total models, battles, votes, rating distribution,
    and most active model.
    """
    db = get_db()
    return await db.get_stats()
