"""API routes for audit log, backup/restore, and comparison reports.

Provides endpoints for:
- GET /api/audit-logs — List audit log entries with filters
- POST /api/backup — Export complete database backup
- POST /api/restore — Restore from backup
- GET /api/reports/comparison/{model_id} — Generate model comparison report
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from evalarena.db.database import Database


def get_db() -> Database:
    """Get database instance -- overridden at app startup."""
    raise RuntimeError("Database not configured")


# -- Audit Log Routes ------------------------------------------------------

audit_router = APIRouter(prefix="/api/audit-logs", tags=["audit"])


@audit_router.get("")
async def list_audit_logs(
    action: str | None = Query(None, description="Filter by action type"),
    entity_type: str | None = Query(None, description="Filter by entity type"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[dict]:
    """List audit log entries.

    Returns recent audit log entries filtered by action and/or entity type.
    Supports pagination via limit and offset.
    """
    db = get_db()
    return await db.list_audit_logs(
        action=action,
        entity_type=entity_type,
        limit=limit,
        offset=offset,
    )


# -- Backup/Restore Routes -------------------------------------------------

backup_router = APIRouter(prefix="/api", tags=["backup"])


class RestoreResult(BaseModel):
    """Result of a restore operation."""

    models_restored: int = 0
    battles_restored: int = 0
    votes_restored: int = 0
    tags_restored: int = 0
    model_tags_restored: int = 0
    templates_restored: int = 0
    webhooks_restored: int = 0
    errors: list[str] = []


@backup_router.post("/backup")
async def create_backup() -> dict:
    """Create a complete backup of all data.

    Exports models, battles, votes, tags, templates, webhooks,
    and tournament data as a single JSON structure.
    The backup can be restored via POST /api/restore.
    """
    db = get_db()
    return await db.create_backup()


@backup_router.post("/restore", response_model=RestoreResult)
async def restore_from_backup(backup: dict) -> RestoreResult:
    """Restore data from a backup.

    Accepts a backup dict (created by POST /api/backup) and restores
    all data idempotently (existing records are skipped).
    """
    db = get_db()
    result = await db.restore_from_backup(backup)
    return RestoreResult(**result)


# -- Comparison Report Routes -----------------------------------------------

report_router = APIRouter(prefix="/api/reports", tags=["reports"])


@report_router.get("/comparison/{model_id}")
async def get_comparison_report(model_id: str) -> dict:
    """Generate a detailed comparison report for a model.

    Includes:
    - Win/loss record against each opponent
    - Rating history with changes
    - Best and worst ratings achieved
    - Per-opponent statistics
    """
    db = get_db()
    report = await db.generate_comparison_report(model_id)
    if report.get("error"):
        raise HTTPException(status_code=404, detail=report["error"])
    return report
