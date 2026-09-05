"""Recommendation explanation service tests."""

from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from app.ai.explanations import RecommendationExplanationService
from app.ai.factory import gemini_api_key_configured
from app.ai.provider import FakeLLMProvider
from app.ai.schemas import RecommendationExplanation
from tests.ai.helpers import sample_explanation_input


def _valid_explanation(**overrides) -> RecommendationExplanation:
    payload = {
        "summary": (
            "Recommended: Create a payment link with an estimated recovery "
            "probability of 82%."
        ),
        "evidence": ["The payment rail shows active degradation."],
        "safety": ["No manual approval is required under current policy."],
        "customer_impact": "The customer receives a clear next step.",
    }
    payload.update(overrides)
    return RecommendationExplanation(**payload)


def test_valid_structured_result_uses_llm_source(recovery_demo_settings) -> None:
    provider = FakeLLMProvider(response=_valid_explanation())
    service = RecommendationExplanationService(
        settings=recovery_demo_settings,
        llm_provider=provider,
    )
    validated = asyncio.run(
        service._generate_with_provider(
            provider=provider,
            input_data=sample_explanation_input(),
        )
    )
    assert validated.summary
    assert provider.call_count == 1


def test_structurally_invalid_extra_field_rejected_by_schema() -> None:
    with pytest.raises(ValidationError):
        RecommendationExplanation.model_validate(
            {
                "summary": "ok",
                "evidence": ["The payment rail shows active degradation."],
                "safety": [],
                "reasoning": "hidden",
            }
        )


@pytest.mark.parametrize(
    ("summary", "evidence"),
    [
        ("Estimated recovery probability: 95%.", ["The payment rail shows active degradation."]),
        (
            "Retry the same payment method is the best next step.",
            ["The payment rail shows active degradation."],
        ),
        (
            "No approval is required for immediate execution.",
            ["The payment rail shows active degradation."],
        ),
        (
            "Razorpay is currently down so use the payment link.",
            ["The customer recently succeeded with this payment method."],
        ),
        (
            "Payment has been captured and the case is recovered.",
            ["The payment rail shows active degradation."],
        ),
    ],
)
def test_semantic_validation_rejects_unsafe_output(
    recovery_demo_settings,
    summary: str,
    evidence: list[str],
) -> None:
    provider = FakeLLMProvider(response=_valid_explanation(summary=summary, evidence=evidence))
    service = RecommendationExplanationService(
        settings=recovery_demo_settings,
        llm_provider=provider,
    )
    input_data = sample_explanation_input()
    if "approval" in summary.lower():
        input_data = sample_explanation_input(
            policy=sample_explanation_input().policy.model_copy(update={"requires_approval": True})
        )
    if "razorpay" in summary.lower():
        input_data = sample_explanation_input(
            evidence_factors=[],
            approved_evidence_statements=[
                "The customer recently succeeded with this payment method."
            ],
        )
    with pytest.raises(Exception):
        asyncio.run(
            service._generate_with_provider(provider=provider, input_data=input_data)
        )


def test_no_key_settings_immediate_fallback(recovery_demo_settings) -> None:
    settings = recovery_demo_settings.model_copy(update={"gemini_api_key": None})
    assert gemini_api_key_configured(settings) is False


def test_transport_deadline_meets_the_provider_minimum() -> None:
    """Gemini rejects any client deadline under ten seconds.

    With `gemini_timeout_seconds` at its 3s default the transport deadline was
    3000ms, and the API answered `400 INVALID_ARGUMENT: Manually set deadline
    3s is too short` to every request -- before the model ran. Because that is
    neither a rate limit nor an auth error it was mapped to a generic
    `AIProviderResponseError`, so production reported `invalid_response` on
    100% of calls and looked like a model that would not comply.
    """
    from app.ai.gemini_provider import (
        GEMINI_MINIMUM_DEADLINE_SECONDS,
        GeminiLLMProvider,
    )
    from app.core.config import Settings

    settings = Settings(
        app_env="test",
        gemini_api_key="fake-key-for-local-assertion-only",
        gemini_timeout_seconds=3.0,
        _env_file=None,
    )
    options = GeminiLLMProvider(settings=settings)._build_http_options()

    assert options.timeout >= GEMINI_MINIMUM_DEADLINE_SECONDS * 1000

    # A longer configured budget must be honoured rather than clamped down to
    # the floor.
    generous = Settings(
        app_env="test",
        gemini_api_key="fake-key-for-local-assertion-only",
        gemini_timeout_seconds=30.0,
        _env_file=None,
    )
    assert GeminiLLMProvider(settings=generous)._build_http_options().timeout == 30_000


def test_our_own_budget_is_independent_of_the_transport_deadline() -> None:
    """The wall-clock cap on the analyze path stays tight.

    Flooring the transport deadline at the provider's minimum must not mean the
    application will now wait ten seconds inside an analyze request. The two
    are separate: `asyncio.wait_for` still enforces the configured budget.
    """
    import asyncio
    import time

    from app.ai.errors import AIProviderTimeoutError
    from app.ai.gemini_provider import GeminiLLMProvider
    from app.ai.schemas import RecommendationExplanation
    from app.core.config import Settings
    from tests.ai.helpers import sample_explanation_input

    settings = Settings(
        app_env="test",
        gemini_api_key="fake-key-for-local-assertion-only",
        gemini_timeout_seconds=0.2,
        _env_file=None,
    )
    provider = GeminiLLMProvider(settings=settings)

    async def never_returns(*_args, **_kwargs):
        await asyncio.sleep(30)

    provider._generate_async = never_returns  # type: ignore[method-assign]

    started = time.perf_counter()
    with pytest.raises(AIProviderTimeoutError):
        asyncio.run(
            provider.generate_structured(
                task="recommendation_explanation",
                input=sample_explanation_input(),
                output_schema=RecommendationExplanation,
            )
        )
    # Bounded by the configured budget, nowhere near the 10s transport floor.
    assert time.perf_counter() - started < 5.0
