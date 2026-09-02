"""Numeric collision and cross-field semantic validation tests."""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from app.ai.explanations import RecommendationExplanationService
from app.ai.provider import FakeLLMProvider
from app.ai.schemas import RecommendationExplanation
from tests.ai.helpers import collision_explanation_input, sample_explanation_input


def _explanation(**overrides) -> RecommendationExplanation:
    payload = {
        "summary": "Recommended: Create a payment link.",
        "evidence": ["The payment rail shows active degradation."],
        "safety": [],
    }
    payload.update(overrides)
    return RecommendationExplanation(**payload)


@pytest.mark.parametrize(
    ("summary", "input_factory"),
    [
        ("Recovery probability is 95%.", collision_explanation_input),
        ("Estimated recovery probability: 82%.", lambda: collision_explanation_input(
            allowed_money_phrases=["INR 95.00", "INR 82.00"],
            allowed_probability_phrases=["70%"],
            success_probability=Decimal("0.70"),
        )),
        ("Confidence is 95%.", lambda: collision_explanation_input(
            allowed_confidence_phrases=["70%"],
        )),
        ("Please pay INR 1,500 to complete.", lambda: sample_explanation_input(
            allowed_money_phrases=["INR 4999.00", "INR 4099.18"],
        )),
        ("Recovery probability is 0.82%.", sample_explanation_input),
    ],
    ids=[
        "amount_probability_collision",
        "recovered_amount_probability_collision",
        "confidence_collision",
        "wrong_money_amount",
        "decimal_probability_format",
    ],
)
def test_numeric_collision_rejected(
    recovery_demo_settings,
    summary: str,
    input_factory,
) -> None:
    provider = FakeLLMProvider(response=_explanation(summary=summary))
    service = RecommendationExplanationService(
        settings=recovery_demo_settings,
        llm_provider=provider,
    )
    input_data = input_factory()
    with pytest.raises(Exception):
        asyncio.run(
            service._generate_with_provider(provider=provider, input_data=input_data)
        )


def test_allowed_probability_phrase_accepted(recovery_demo_settings) -> None:
    provider = FakeLLMProvider(
        response=_explanation(summary="Estimated recovery probability: 82%.")
    )
    service = RecommendationExplanationService(
        settings=recovery_demo_settings,
        llm_provider=provider,
    )
    result = asyncio.run(
        service._generate_with_provider(
            provider=provider,
            input_data=sample_explanation_input(),
        )
    )
    assert "82%" in result.summary


def test_allowed_money_phrase_accepted(recovery_demo_settings) -> None:
    provider = FakeLLMProvider(
        response=_explanation(
            summary="Recommended action for INR 4999.00 at risk.",
            evidence=["The payment rail shows active degradation."],
        )
    )
    service = RecommendationExplanationService(
        settings=recovery_demo_settings,
        llm_provider=provider,
    )
    result = asyncio.run(
        service._generate_with_provider(
            provider=provider,
            input_data=sample_explanation_input(),
        )
    )
    assert "4999.00" in result.summary


@pytest.mark.parametrize(
    ("field_overrides", "input_overrides"),
    [
        (
            {"evidence": ["Retry the same payment method is the best next step."]},
            {},
        ),
        (
            {"safety": ["No approval is required for immediate execution."]},
            {
                "policy": sample_explanation_input().policy.model_copy(
                    update={"requires_approval": True}
                )
            },
        ),
        (
            {"evidence": ["Payment has been captured and recovered."]},
            {},
        ),
        (
            {"customer_impact": "Razorpay is currently down so wait."},
            {"evidence_factors": [], "approved_evidence_statements": []},
        ),
        (
            {"safety": ["Recovery probability is 95%."]},
            {},
        ),
    ],
    ids=[
        "wrong_action_in_evidence",
        "approval_contradiction_in_safety",
        "recovered_claim_in_evidence",
        "provider_outage_in_customer_impact",
        "numeric_in_safety",
    ],
)
def test_cross_field_unsafe_claims_rejected(
    recovery_demo_settings,
    field_overrides,
    input_overrides,
) -> None:
    provider = FakeLLMProvider(response=_explanation(**field_overrides))
    service = RecommendationExplanationService(
        settings=recovery_demo_settings,
        llm_provider=provider,
    )
    input_data = sample_explanation_input(**input_overrides)
    with pytest.raises(Exception):
        asyncio.run(
            service._generate_with_provider(provider=provider, input_data=input_data)
        )
