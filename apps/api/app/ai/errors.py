"""AI provider failure classifications (Prompt 17)."""

from __future__ import annotations


class AIProviderError(Exception):
    """Base class for optional LLM enrichment failures."""

    category: str = "provider_error"


class AIProviderUnavailableError(AIProviderError):
    category = "unavailable"


class AIProviderTimeoutError(AIProviderError):
    category = "timeout"


class AIProviderRateLimitError(AIProviderError):
    category = "rate_limit"


class AIProviderAuthError(AIProviderError):
    category = "auth"


class AIProviderResponseError(AIProviderError):
    category = "invalid_response"


class AISemanticValidationError(AIProviderError):
    category = "semantic_validation"
