"""API routes for dashboard analytics.

Provides rating distribution histograms, activity trends,
and top movers (gainers/losers) for the admin dashboard.
"""

from fastapi import APIRouter, Query

from evalarena.db.database import Database
from evalarena.db.models import (
    ActivityTrend,
    DashboardStats,
    RatingDecayConfig,
    RatingDecayResult,
    RatingDistribution,
    TopMover,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def get_db() -> Database:
    """Get database instance -- overridden at app startup."""
    raise RuntimeError("Database not configured")


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(period_days: int = Query(default=7, ge=1, le=365)) -> DashboardStats:
    """Get full dashboard analytics.

    Returns rating distribution histogram, daily activity trends,
    and top rating gainers/losers over the specified period.
    """
    db = get_db()

    dist_data = await db.get_rating_distribution()
    trends_data = await db.get_activity_trends(days=min(period_days * 2, 30))
    gainers, losers = await db.get_top_movers(days=period_days)

    return DashboardStats(
        rating_distribution=RatingDistribution(
            buckets=[],
            total_models=dist_data["total_models"],
            mean_rating=dist_data["mean_rating"],
            median_rating=dist_data["median_rating"],
        ),
        activity_trends=[ActivityTrend(**t) for t in trends_data],
        top_gainers=[TopMover(**g) for g in gainers],
        top_losers=[TopMover(**l) for l in losers],
        period_days=period_days,
    )


@router.get("/rating-distribution", response_model=RatingDistribution)
async def get_rating_distribution() -> RatingDistribution:
    """Get rating distribution histogram.

    Returns bucketed rating distribution showing how many models
    fall in each 100-point rating range.
    """
    db = get_db()
    data = await db.get_rating_distribution()
    return RatingDistribution(**data)


@router.get("/activity-trends", response_model=list[ActivityTrend])
async def get_activity_trends(days: int = Query(default=14, ge=1, le=90)) -> list[ActivityTrend]:
    """Get daily battle and vote activity over the last N days."""
    db = get_db()
    data = await db.get_activity_trends(days=days)
    return [ActivityTrend(**d) for d in data]


@router.get("/top-movers")
async def get_top_movers(
    days: int = Query(default=7, ge=1, le=365),
    limit: int = Query(default=5, ge=1, le=20),
) -> dict:
    """Get top rating gainers and losers over the specified period.

    Useful for identifying which models are improving or declining
    in the recent evaluation period.
    """
    db = get_db()
    gainers, losers = await db.get_top_movers(days=days, limit=limit)
    return {
        "period_days": days,
        "top_gainers": gainers,
        "top_losers": losers,
    }


@router.post("/apply-decay", response_model=dict)
async def apply_rating_decay(config: RatingDecayConfig = RatingDecayConfig()) -> dict:
    """Apply rating decay to inactive models.

    Models that haven't participated in battles for the specified number
    of days will have their rating gradually reduced toward the baseline.

    This prevents stale ratings from dominating the leaderboard when
    models are no longer actively evaluated.
    """
    db = get_db()
    result = await db.apply_rating_decay(
        inactive_days=config.inactive_days,
        decay_rate=config.decay_rate,
        min_rating=config.min_rating,
    )
    return {
        "models_affected": result["models_affected"],
        "total_rating_decayed": result["total_rating_decayed"],
        "details": [d if isinstance(d, dict) else d.model_dump() for d in result["details"]],
    }
