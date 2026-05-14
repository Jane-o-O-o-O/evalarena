"""API routes for voting.

Supports optional vote comments for qualitative feedback alongside
the binary/tie choice. Fires webhooks on vote events.
"""

from fastapi import APIRouter, HTTPException, Request

from evalarena.db.database import Database
from evalarena.db.models import VoteCreate, VoteOut

router = APIRouter(prefix="/api/vote", tags=["vote"])


def get_db() -> Database:
    raise RuntimeError("Database not configured")


@router.post("", response_model=VoteOut, status_code=201)
async def submit_vote(data: VoteCreate, request: Request) -> VoteOut:
    """Submit a vote for a battle.

    Each battle can only be voted on once per IP address. Voting triggers
    ELO rating updates for both models. An optional ``comment`` field allows
    voters to explain their reasoning.

    Fires registered webhooks with event type ``vote``.
    """
    from evalarena.webhooks import fire_webhooks

    db = get_db()
    voter_ip = request.client.host if request.client else None
    try:
        recorded = await db.create_vote(data, voter_ip=voter_ip)
    except ValueError as e:
        error_msg = str(e)
        if "already voted" in error_msg:
            raise HTTPException(status_code=409, detail=error_msg)
        raise HTTPException(status_code=404, detail=error_msg)

    if not recorded:
        raise HTTPException(status_code=409, detail="This battle has already been voted on")

    battle = await db.get_battle(data.battle_id)

    # Fire webhook notifications (non-blocking)
    try:
        webhooks = await db.get_active_webhooks("vote")
        if webhooks:
            await fire_webhooks(webhooks, "vote", {
                "battle_id": data.battle_id,
                "winner": data.winner.value,
                "comment": getattr(data, "comment", "") or "",
            })
    except Exception:
        pass  # Don't fail the vote if webhooks fail

    return VoteOut(
        id="recorded",
        battle_id=data.battle_id,
        winner=data.winner.value,
        comment=getattr(data, "comment", "") or "",
        created_at=battle["created_at"] if battle else "",
    )
