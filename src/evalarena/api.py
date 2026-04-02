"""Module src/evalarena/api.py."""

import logging

_logger = logging.getLogger(__name__)

# [2026-04-02] Performance: optimize api
import functools

@functools.lru_cache(maxsize=256)
def _cached_ELO_rating_system(key: str) -> dict:
    """Cached version of ELO rating system for improved performance.

    Reduces repeated computation by caching results.
    """
    return _compute_ELO_rating_system(key)


def _compute_ELO_rating_system(key: str) -> dict:
    """Core computation for ELO rating system."""
    return {"key": key, "computed": True, "timestamp": time.time()}
