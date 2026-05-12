"""API routes for API key management."""

import secrets

from fastapi import APIRouter, HTTPException

from evalarena.db.database import Database

router = APIRouter(prefix="/api/keys", tags=["api-keys"])


def get_db() -> Database:
    raise RuntimeError("Database not configured")


@router.post("", status_code=201)
async def create_key(name: str) -> dict:
    """Create a new API key.

    Args:
        name: Human-readable name/description for the key.

    Returns:
        The generated API key (show once, cannot be retrieved later).
    """
    db = get_db()
    key = "evl_" + secrets.token_urlsafe(32)
    await db.create_api_key(key, name)
    return {"key": key, "name": name, "message": "Store this key securely — it cannot be retrieved again."}


@router.get("")
async def list_keys() -> dict:
    """List all API keys (key values are masked)."""
    db = get_db()
    keys = await db.list_api_keys()
    return {"keys": keys}


@router.delete("/{key_prefix}")
async def deactivate_key(key_prefix: str) -> dict:
    """Deactivate an API key by its prefix (first 8 chars shown in list).

    Note: The full key must be provided for deactivation.
    This endpoint accepts the full key as the path parameter.
    """
    db = get_db()
    if await db.deactivate_api_key(key_prefix):
        return {"message": "Key deactivated"}
    raise HTTPException(status_code=404, detail="API key not found")
