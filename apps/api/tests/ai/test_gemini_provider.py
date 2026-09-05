"""Gemini provider adapter tests with stub SDK client."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pydantic import SecretStr

from app.ai.errors import AIProviderRateLimitError, AIProviderTimeoutError
from app.ai.gemini_provider import (
    GEMINI_MINIMUM_DEADLINE_SECONDS,
    GeminiLLMProvider,
)
from app.ai.schemas import RecommendationExplanation
from app.core.config import Settings
from tests.ai.helpers import sample_explanation_input

_VALID_JSON = (
    '{"summary":"ok","evidence":["The payment rail shows active degradation."],"safety":[]}'
)


class _StubAsyncModels:
    def __init__(self, handler) -> None:
        self._handler = handler
        self.call_count = 0
        self.last_kwargs: dict[str, Any] | None = None

    async def generate_content(self, **kwargs):
        self.call_count += 1
        self.last_kwargs = kwargs
        return await self._handler(**kwargs)


class _StubAio:
    def __init__(self, handler) -> None:
        self.models = _StubAsyncModels(handler)


class StubGeminiClient:
    def __init__(self, handler) -> None:
        self.aio = _StubAio(handler)
        self.http_options = None
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _settings(**overrides) -> Settings:
    base = {
        "gemini_api_key": SecretStr("real-secret-key-value"),
        "gemini_model_name": "gemini-3.6-flash",
        "gemini_timeout_seconds": 0.05,
    }
    base.update(overrides)
    return Settings(**base)


def test_structured_output_request_uses_json_schema() -> None:
    expected_schema = RecommendationExplanation.model_json_schema()

    async def handler(**kwargs):
        config = kwargs["config"]
        assert kwargs["model"] == "gemini-3.6-flash"
        assert config.response_mime_type == "application/json"
        assert config.response_json_schema == expected_schema
        assert config.response_schema is None
        assert config.temperature is None
        assert config.top_p is None
        assert config.top_k is None
        return type("Resp", (), {"text": _VALID_JSON})()

    client = StubGeminiClient(handler)
    provider = GeminiLLMProvider(settings=_settings(), client=client)
    result = asyncio.run(
        provider.generate_structured(
            task="recommendation_explanation",
            input=sample_explanation_input(),
            output_schema=RecommendationExplanation,
        )
    )
    assert result.summary == "ok"
    assert client.aio.models.call_count == 1
    assert client.aio.models.last_kwargs is not None
    assert client.aio.models.last_kwargs["model"] == "gemini-3.6-flash"


def test_custom_model_name_passed_through(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_MODEL_NAME", "custom-compatible-model")
    settings = Settings(gemini_api_key=SecretStr("real-secret-key-value"))

    async def handler(**kwargs):
        return type("Resp", (), {"text": _VALID_JSON})()

    client = StubGeminiClient(handler)
    provider = GeminiLLMProvider(settings=settings, client=client)
    asyncio.run(
        provider.generate_structured(
            task="recommendation_explanation",
            input=sample_explanation_input(),
            output_schema=RecommendationExplanation,
        )
    )
    assert client.aio.models.last_kwargs is not None
    assert client.aio.models.last_kwargs["model"] == "custom-compatible-model"


def test_provider_timeout_raises_without_retry() -> None:
    async def slow_handler(**kwargs):
        await asyncio.sleep(0.2)
        return type("Resp", (), {"text": "{}"})()

    client = StubGeminiClient(slow_handler)
    provider = GeminiLLMProvider(settings=_settings(gemini_timeout_seconds=0.05), client=client)
    with pytest.raises(AIProviderTimeoutError):
        asyncio.run(
            provider.generate_structured(
                task="recommendation_explanation",
                input=sample_explanation_input(),
                output_schema=RecommendationExplanation,
            )
        )
    assert client.aio.models.call_count == 1


def test_provider_error_does_not_retry() -> None:
    async def failing_handler(**kwargs):
        raise RuntimeError("429 rate limit exceeded")

    client = StubGeminiClient(failing_handler)
    provider = GeminiLLMProvider(settings=_settings(), client=client)
    with pytest.raises(AIProviderRateLimitError):
        asyncio.run(
            provider.generate_structured(
                task="recommendation_explanation",
                input=sample_explanation_input(),
                output_schema=RecommendationExplanation,
            )
        )
    assert client.aio.models.call_count == 1


def test_http_options_use_single_attempt_and_a_valid_deadline() -> None:
    """The transport deadline is floored at the provider's own minimum.

    This test previously asserted `timeout == 3000`, which codified a bug: the
    Gemini API rejects any client-set deadline below ten seconds with
    `400 INVALID_ARGUMENT`, so a 3s deadline failed 100% of calls before the
    model ran. The application's own wall-clock budget is enforced separately
    by `asyncio.wait_for` and is unaffected -- see
    `test_our_own_budget_is_independent_of_the_transport_deadline`.
    """
    provider = GeminiLLMProvider(settings=_settings(gemini_timeout_seconds=3.0))
    options = provider._build_http_options()
    assert options.timeout == int(GEMINI_MINIMUM_DEADLINE_SECONDS * 1000)
    assert options.retry_options is not None
    assert options.retry_options.attempts == 1


def test_lazy_client_uses_http_options(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.aio = self
            self.models = self

        async def generate_content(self, **kwargs):
            return type(
                "Resp",
                (),
                {
                    "text": (
                        '{"summary":"ok","evidence":["The payment rail shows active '
                        'degradation."],"safety":[]}'
                    )
                },
            )()

    import google.genai as genai_module

    monkeypatch.setattr(genai_module, "Client", FakeClient)
    provider = GeminiLLMProvider(settings=_settings())
    asyncio.run(
        provider.generate_structured(
            task="t",
            input=sample_explanation_input(),
            output_schema=RecommendationExplanation,
        )
    )
    assert "http_options" in captured
    options = captured["http_options"]
    # Floored to the provider minimum rather than the tiny test budget, for the
    # reason documented on `_build_http_options`.
    assert options.timeout == int(GEMINI_MINIMUM_DEADLINE_SECONDS * 1000)
    assert options.retry_options.attempts == 1
