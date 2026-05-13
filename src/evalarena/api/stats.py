"""API routes for platform statistics.

Includes aggregate stats, per-category breakdowns, and model
comparison matrix.
"""

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


@router.get("/categories")
async def get_category_stats() -> list[dict]:
    """Get per-category statistics.

    Returns model count, average rating, highest rating,
    total battles, and total votes for each category.
    """
    db = get_db()
    return await db.get_category_stats()


@router.get("/comparison-matrix")
async def get_comparison_matrix() -> dict:
    """Get a pairwise model comparison matrix.

    Returns all models and their head-to-head records against each other.
    Useful for building a comparison heatmap or matrix view.
    """
    db = get_db()
    return await db.get_comparison_matrix()
