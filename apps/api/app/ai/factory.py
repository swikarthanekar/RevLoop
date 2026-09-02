"""Provider factory helpers."""

from __future__ import annotations

from app.ai.gemini_provider import GeminiLLMProvider
from app.ai.provider import LLMProvider
from app.core.config import Settings

_PLACEHOLDER_PREFIXES = ("dev-", "test-", "placeholder-")


def gemini_api_key_configured(settings: Settings) -> bool:
    secret = settings.gemini_api_key
    if secret is None:
        return False
    value = secret.get_secret_value().strip()
    if not value:
        return False
    lowered = value.lower()
    return not any(lowered.startswith(prefix) for prefix in _PLACEHOLDER_PREFIXES)


def create_llm_provider(settings: Settings) -> LLMProvider | None:
    if settings.llm_provider.lower() != "gemini":
        return None
    if not gemini_api_key_configured(settings):
        return None
    return GeminiLLMProvider(settings=settings)
