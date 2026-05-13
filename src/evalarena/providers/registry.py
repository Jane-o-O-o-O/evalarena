"""Provider registry for managing LLM provider instances.

Providers self-register on import, and are looked up by name at auto-battle time.
"""

from __future__ import annotations

from evalarena.providers.base import LLMProvider

# Global registry: provider_name -> provider instance
_registry: dict[str, LLMProvider] = {}


def register_provider(provider: LLMProvider) -> None:
    """Register an LLM provider instance.

    Args:
        provider: The provider to register. Uses ``provider.name`` as the key.
    """
    _registry[provider.name] = provider


def get_provider(name: str) -> LLMProvider | None:
    """Get a registered provider by name.

    Args:
        name: Provider name (e.g. 'openai', 'anthropic').

    Returns:
        The provider instance, or None if not registered.
    """
    return _registry.get(name)


def list_providers() -> list[dict]:
    """List all registered providers with their configuration status.

    Returns:
        List of dicts with 'name' and 'configured' keys.
    """
    return [
        {"name": name, "configured": provider.is_configured()}
        for name, provider in _registry.items()
    ]
