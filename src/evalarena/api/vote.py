"""API routes for voting."""

from fastapi import APIRouter, HTTPException, Request

from evalarena.db.database import Database
from evalarena.db.models import VoteCreate, VoteOut

router = APIRouter(prefix="/api/vote", tags=["vote"])


def get_db() -> Database:
    raise RuntimeError("Database not configured")


@router.post("", response_model=VoteOut, status_code=201)
async def submit_vote(data: VoteCreate, request: Request) -> VoteOut:
    """Submit a vote for a battle.

    Each battle can only be voted on once. Voting triggers ELO rating updates
    for both models.
    """
    db = get_db()
    voter_ip = request.client.host if request.client else None
    try:
        recorded = await db.create_vote(data, voter_ip=voter_ip)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if not recorded:
        raise HTTPException(status_code=409, detail="This battle has already been voted on")

    battle = await db.get_battle(data.battle_id)
    return VoteOut(
        id="recorded",
        battle_id=data.battle_id,
        winner=data.winner.value,
        created_at=battle["created_at"] if battle else "",
    )
