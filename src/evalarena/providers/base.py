"""Abstract base class for LLM providers.

All LLM provider integrations (OpenAI, Anthropic, etc.) implement this
interface so the arena can auto-sample responses from any registered model.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    """Response from an LLM provider call."""

    text: str
    """The generated text content."""

    model_id: str
    """The model identifier used for the API call."""

    tokens_used: int = 0
    """Total tokens consumed (prompt + completion)."""

    latency_ms: float = 0.0
    """Request latency in milliseconds."""


class LLMProvider(ABC):
    """Abstract LLM provider interface.

    Subclasses must implement ``generate`` to call the actual LLM API.
    Providers are registered via ``register_provider`` and resolved
    at auto-battle time via ``get_provider``.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name (e.g. 'openai', 'anthropic')."""

    @abstractmethod
    async def generate(self, prompt: str, model: str, **kwargs) -> LLMResponse:
        """Generate a response from the given model.

        Args:
            prompt: The user prompt to send.
            model: The model identifier (e.g. 'gpt-4o', 'claude-3.5-sonnet').
            **kwargs: Provider-specific options (temperature, max_tokens, etc.)

        Returns:
            LLMResponse with the generated text and metadata.

        Raises:
            ProviderError: If the API call fails.
        """

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if this provider has valid credentials configured.

        Returns:
            True if the provider can make API calls (e.g. API key is set).
        """


class ProviderError(Exception):
    """Raised when an LLM provider API call fails."""
