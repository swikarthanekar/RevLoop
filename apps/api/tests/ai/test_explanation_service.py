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
