"""API routes for LLM provider management."""

from fastapi import APIRouter

from evalarena.providers import list_providers

router = APIRouter(prefix="/api/providers", tags=["providers"])


@router.get("")
async def get_providers() -> list[dict]:
    """List all registered LLM providers and their configuration status.

    Returns:
        List of provider dicts with 'name' and 'configured' keys.
    """
    return list_providers()
