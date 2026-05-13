"""Anthropic LLM provider adapter.

Calls the Anthropic Messages API to generate model responses.
Requires the ``httpx`` package and ``ANTHROPIC_API_KEY`` environment variable.
"""

from __future__ import annotations

import os
import time

from evalarena.providers.base import LLMProvider, LLMResponse, ProviderError


class AnthropicProvider(LLMProvider):
    """Anthropic Messages API provider.

    Supports models like claude-3.5-sonnet, claude-3-opus, claude-3-haiku, etc.
    """

    def __init__(self, api_key: str | None = None) -> None:
        """Initialize the Anthropic provider.

        Args:
            api_key: Anthropic API key. Falls back to ``ANTHROPIC_API_KEY`` env var.
        """
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    @property
    def name(self) -> str:
        return "anthropic"

    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def generate(self, prompt: str, model: str, **kwargs) -> LLMResponse:
        """Generate a response using Anthropic's Messages API.

        Args:
            prompt: The user prompt.
            model: Model identifier (e.g. 'claude-3-5-sonnet-20241022').
            **kwargs: Optional 'temperature', 'max_tokens'.

        Returns:
            LLMResponse with generated text and metadata.

        Raises:
            ProviderError: If the API call fails.
        """
        try:
            import httpx
        except ImportError:
            raise ProviderError("httpx package required for Anthropic provider")

        if not self._api_key:
            raise ProviderError("Anthropic API key not configured (set ANTHROPIC_API_KEY)")

        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        body: dict = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": kwargs.get("max_tokens", 2048),
        }
        if "temperature" in kwargs:
            body["temperature"] = kwargs["temperature"]

        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(url, json=body, headers=headers)
                resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise ProviderError(f"Anthropic API error {e.response.status_code}: {e.response.text[:200]}")
        except Exception as e:
            raise ProviderError(f"Anthropic API request failed: {e}")

        elapsed_ms = (time.monotonic() - start) * 1000
        data = resp.json()

        text = data["content"][0]["text"]
        usage = data.get("usage", {})
        tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)

        return LLMResponse(
            text=text,
            model_id=model,
            tokens_used=tokens,
            latency_ms=round(elapsed_ms, 1),
        )
