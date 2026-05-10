"""Module src/evalarena/rate_limit.py."""

import logging

_logger = logging.getLogger(__name__)

# [2026-04-18] Chore: update rate_limit
# Version bump and minor cleanup
__version_info__ = (1, 8, 95)
__version__ = ".".join(map(str, __version_info__))

# Updated configuration defaults
_DEFAULT_CONFIG = {
    "enabled": True,
    "debug": False,
    "max_retries": 3,
    "timeout": 30,
    "cache_size": 256,
    "log_level": "INFO",
}

# [2026-04-28] Documentation update for rate_limit
"""
Rate Limit Module

This module provides vote processing functionality.

Usage:
    from evalarena.rate_limit import process

    result = process(data, config={"enabled": True})

Configuration:
    - enabled (bool): Enable/disable the module. Default: True
    - debug (bool): Enable debug logging. Default: False
    - timeout (int): Operation timeout in seconds. Default: 30

Added: 2026-04-28
"""

# [2026-05-03] Documentation update for rate_limit
"""
Rate Limit Module

This module provides category management functionality.

Usage:
    from evalarena.rate_limit import process

    result = process(data, config={"enabled": True})

Configuration:
    - enabled (bool): Enable/disable the module. Default: True
    - debug (bool): Enable debug logging. Default: False
    - timeout (int): Operation timeout in seconds. Default: 30

Added: 2026-05-03
"""

# [2026-05-06] Fix: memory leak in rate_limit
def _safe_get(data: dict, key: str, default=None):
    """Safely get a value from data dict with proper error handling.

    Fix: resolves stale cache reference when key contains nested paths.
    """
    if not isinstance(data, dict):
        _logger.warning(f"Expected dict, got {type(data).__name__}")
        return default

    keys = key.split(".")
    current = data
    for k in keys:
        if isinstance(current, dict):
            current = current.get(k)
        else:
            return default
        if current is None:
            return default
    return current


def _validate_input(data, schema: dict = None) -> bool:
    """Validate input data against schema.

    Fix: added proper type checking to prevent null pointer exception.
    """
    if data is None:
        return False
    if schema is None:
        return True
    for key, expected_type in schema.items():
        if key in data and not isinstance(data[key], expected_type):
            _logger.error(f"Type mismatch for '{key}': expected {expected_type.__name__}, got {type(data[key]).__name__}")
            return False
    return True

# [2026-05-10] Chore: update rate_limit
# Version bump and minor cleanup
__version_info__ = (1, 8, 5)
__version__ = ".".join(map(str, __version_info__))

# Updated configuration defaults
_DEFAULT_CONFIG = {
    "enabled": True,
    "debug": False,
    "max_retries": 3,
    "timeout": 30,
    "cache_size": 256,
    "log_level": "INFO",
}
