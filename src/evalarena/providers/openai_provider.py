"""OpenAI LLM provider adapter.

Calls the OpenAI Chat Completions API to generate model responses.
Requires the ``openai`` package and ``OPENAI_API_KEY`` environment variable.
"""

from __future__ import annotations

import os
import time

from evalarena.providers.base import LLMProvider, LLMResponse, ProviderError


class OpenAIProvider(LLMProvider):
    """OpenAI Chat Completions provider.

    Supports models like gpt-4o, gpt-4o-mini, gpt-3.5-turbo, o1, etc.
    """

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        """Initialize the OpenAI provider.

        Args:
            api_key: OpenAI API key. Falls back to ``OPENAI_API_KEY`` env var.
            base_url: Optional custom base URL for OpenAI-compatible APIs.
        """
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._base_url = base_url

    @property
    def name(self) -> str:
        return "openai"

    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def generate(self, prompt: str, model: str, **kwargs) -> LLMResponse:
        """Generate a response using OpenAI's Chat Completions API.

        Args:
            prompt: The user prompt.
            model: Model identifier (e.g. 'gpt-4o', 'gpt-4o-mini').
            **kwargs: Optional 'temperature', 'max_tokens'.

        Returns:
            LLMResponse with generated text and metadata.

        Raises:
            ProviderError: If the API call fails.
        """
        try:
            import httpx
        except ImportError:
            raise ProviderError("httpx package required for OpenAI provider")

        if not self._api_key:
            raise ProviderError("OpenAI API key not configured (set OPENAI_API_KEY)")

        url = (self._base_url or "https://api.openai.com/v1") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        body: dict = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        }
        if "temperature" in kwargs:
            body["temperature"] = kwargs["temperature"]
        if "max_tokens" in kwargs:
            body["max_tokens"] = kwargs["max_tokens"]

        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(url, json=body, headers=headers)
                resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise ProviderError(f"OpenAI API error {e.response.status_code}: {e.response.text[:200]}")
        except Exception as e:
            raise ProviderError(f"OpenAI API request failed: {e}")

        elapsed_ms = (time.monotonic() - start) * 1000
        data = resp.json()

        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        tokens = usage.get("total_tokens", 0)

        return LLMResponse(
            text=text,
            model_id=model,
            tokens_used=tokens,
            latency_ms=round(elapsed_ms, 1),
        )
