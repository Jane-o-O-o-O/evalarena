"""API routes for battle search, win streaks, and webhooks."""

from fastapi import APIRouter, HTTPException, Query

from evalarena.db.database import Database
from evalarena.db.models import WebhookCreate

router = APIRouter(tags=["search", "streaks", "webhooks"])


def get_db() -> Database:
    """Get database instance -- overridden at app startup."""
    raise RuntimeError("Database not configured")


# -- Battle Search --------------------------------------------------------


@router.get("/api/battles/search")
async def search_battles(
    q: str = Query(..., min_length=1, max_length=200, description="Search query"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
) -> list[dict]:
    """Search battles by prompt or response content.

    Returns battles matching the query, with prompt matches ranked higher
    than response-only matches.
    """
    db = get_db()
    return await db.search_battles(q, limit=limit)


# -- Win Streaks ----------------------------------------------------------


@router.get("/api/streaks")
async def get_win_streaks() -> list[dict]:
    """Get win/loss streak leaderboard for all models.

    Returns each model's current streak, best win streak, and best loss streak.
    Sorted by best win streak descending.
    """
    db = get_db()
    return await db.get_win_streaks()


@router.get("/api/models/{model_id}/streak")
async def get_model_streak(model_id: str) -> dict:
    """Get win streak info for a specific model."""
    db = get_db()
    model = await db.get_model(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    streak = await db.get_model_streak(model_id)
    if not streak:
        raise HTTPException(status_code=404, detail="Streak data not found")
    return streak


# -- Webhooks -------------------------------------------------------------


@router.post("/api/webhooks", status_code=201)
async def create_webhook(data: WebhookCreate) -> dict:
    """Register a new webhook.

    The webhook URL will receive a POST request when the specified event occurs.
    Supported events: ``vote``, ``battle``, ``tournament``.
    """
    db = get_db()
    return await db.create_webhook(
        url=data.url, event=data.event, secret=data.secret,
    )


@router.get("/api/webhooks")
async def list_webhooks(
    event: str | None = Query(None, description="Filter by event type"),
) -> list[dict]:
    """List all registered webhooks."""
    db = get_db()
    return await db.list_webhooks(event=event)


@router.delete("/api/webhooks/{webhook_id}")
async def delete_webhook(webhook_id: str) -> dict:
    """Delete a webhook."""
    db = get_db()
    deleted = await db.delete_webhook(webhook_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {"deleted": True, "webhook_id": webhook_id}
