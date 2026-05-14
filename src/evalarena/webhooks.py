"""Webhook notification dispatcher.

Fires HTTP POST requests to registered webhook URLs when events occur.
Runs asynchronously in the background so it doesn't block the response.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from typing import Any

import httpx

logger = logging.getLogger("evalarena.webhooks")


async def dispatch_webhook(url: str, payload: dict[str, Any], secret: str = "") -> None:
    """Send a webhook notification.

    Args:
        url: The callback URL.
        payload: JSON payload to send.
        secret: Optional HMAC secret for signing.
    """
    headers: dict[str, str] = {"Content-Type": "application/json"}
    body = json.dumps(payload, ensure_ascii=False)

    if secret:
        signature = hmac.new(
            secret.encode(), body.encode(), hashlib.sha256
        ).hexdigest()
        headers["X-Webhook-Signature"] = f"sha256={signature}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, content=body, headers=headers)
            if response.status_code >= 400:
                logger.warning(
                    "Webhook %s returned status %d: %s",
                    url, response.status_code, response.text[:200],
                )
            else:
                logger.debug("Webhook %s delivered (%d)", url, response.status_code)
    except Exception as e:
        logger.warning("Webhook %s failed: %s", url, str(e))


async def fire_webhooks(
    webhooks: list[dict[str, Any]],
    event: str,
    payload: dict[str, Any],
) -> None:
    """Fire all matching webhooks in the background.

    Args:
        webhooks: List of webhook dicts (from DB).
        event: The event type.
        payload: The event payload.
    """
    if not webhooks:
        return

    payload_with_event = {**payload, "event": event}

    tasks = [
        dispatch_webhook(
            url=wh["url"],
            payload=payload_with_event,
            secret=wh.get("secret", ""),
        )
        for wh in webhooks
    ]

    # Fire and forget - don't block the response
    for task in tasks:
        asyncio.create_task(task)
