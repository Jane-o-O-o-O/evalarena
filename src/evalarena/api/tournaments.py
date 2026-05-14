"""API routes for tournaments.

Round-robin tournament system where all model pairs compete.
Each match consists of one or more blind battles.
"""

from fastapi import APIRouter, HTTPException, Query

from evalarena.db.database import Database
from evalarena.db.models import TournamentCreate

router = APIRouter(prefix="/api/tournaments", tags=["tournaments"])


def get_db() -> Database:
    """Get database instance -- overridden at app startup."""
    raise RuntimeError("Database not configured")


@router.post("", status_code=201)
async def create_tournament(data: TournamentCreate) -> dict:
    """Create a round-robin tournament.

    Automatically generates all pairwise matches for the given models.
    Each match will have ``prompts_per_match`` blind battles.
    """
    db = get_db()

    # Validate all models exist
    for mid in data.model_ids:
        model = await db.get_model(mid)
        if not model:
            raise HTTPException(status_code=404, detail=f"Model '{mid}' not found")

    # Check for duplicates
    if len(set(data.model_ids)) != len(data.model_ids):
        raise HTTPException(status_code=400, detail="Duplicate model IDs in list")

    tournament = await db.create_tournament(
        name=data.name,
        model_ids=data.model_ids,
        category=data.category,
        prompts_per_match=data.prompts_per_match,
        prompt_template_id=data.prompt_template_id,
    )
    return tournament


@router.get("")
async def list_tournaments(
    status: str | None = Query(None, description="Filter by status (pending/in_progress/completed/cancelled)"),
) -> list[dict]:
    """List all tournaments."""
    db = get_db()
    return await db.list_tournaments(status=status)


@router.get("/{tournament_id}")
async def get_tournament(tournament_id: str) -> dict:
    """Get tournament details including standings and match results."""
    db = get_db()
    tournament = await db.get_tournament(tournament_id)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    return tournament


@router.post("/{tournament_id}/start")
async def start_tournament(tournament_id: str) -> dict:
    """Start a pending tournament (change status to in_progress)."""
    db = get_db()
    success = await db.start_tournament(tournament_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Tournament not found or not in pending status",
        )
    return {"status": "in_progress", "tournament_id": tournament_id}


@router.post("/{tournament_id}/complete")
async def complete_tournament(tournament_id: str) -> dict:
    """Mark a tournament as completed."""
    db = get_db()
    success = await db.complete_tournament(tournament_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Tournament not found or not in progress",
        )
    return {"status": "completed", "tournament_id": tournament_id}


@router.post("/{tournament_id}/cancel")
async def cancel_tournament(tournament_id: str) -> dict:
    """Cancel a tournament."""
    db = get_db()
    success = await db.cancel_tournament(tournament_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Tournament not found or already completed",
        )
    return {"status": "cancelled", "tournament_id": tournament_id}
