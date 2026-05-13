"""Mock LLM provider for testing and development.

Returns configurable canned responses without making any API calls.
Useful for testing the auto-battle pipeline and for development.
"""

from __future__ import annotations

import time

from evalarena.providers.base import LLMProvider, LLMResponse


class MockProvider(LLMProvider):
    """Mock provider that returns a deterministic response based on the prompt.

    Always configured (no API key needed). Useful for testing.
    """

    def __init__(self) -> None:
        self._call_count = 0

    @property
    def name(self) -> str:
        return "mock"

    def is_configured(self) -> bool:
        return True

    async def generate(self, prompt: str, model: str, **kwargs) -> LLMResponse:
        """Generate a mock response.

        Args:
            prompt: The user prompt.
            model: Model identifier.

        Returns:
            LLMResponse with a deterministic mock response.
        """
        self._call_count += 1
        start = time.monotonic()
        text = (
            f"[Mock response from {model}] "
            f"Regarding your question about '{prompt[:50]}...': "
            f"This is a simulated response for testing purposes. "
            f"(call #{self._call_count})"
        )
        elapsed_ms = (time.monotonic() - start) * 1000
        return LLMResponse(
            text=text,
            model_id=model,
            tokens_used=len(prompt.split()) + len(text.split()),
            latency_ms=round(elapsed_ms, 1),
        )
