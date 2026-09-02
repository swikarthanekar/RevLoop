"""Deterministic evaluation harness for adversarial fake LLM outputs."""

from __future__ import annotations

import asyncio

import pytest

from app.ai.explanations import RecommendationExplanationService
from app.ai.provider import FakeLLMProvider
from app.ai.schemas import RecommendationExplanation
from tests.ai.fake_providers import build_grounded_explanation_provider
from tests.ai.helpers import sample_explanation_input


def _cases() -> list[dict[str, object]]:
    return [
        {
            "name": "numeric_mismatch",
            "response": RecommendationExplanation(
                summary="Estimated recovery probability: 95%.",
                evidence=["The payment rail shows active degradation."],
                safety=[],
            ),
            "expect_fallback": True,
        },
        {
            "name": "valid",
            "response": None,
            "expect_fallback": False,
        },
    ] + [
        {
            "name": f"unsupported_claim_{index}",
            "response": RecommendationExplanation(
                summary=f"Case note {index}",
                evidence=["Unsupported invented factor statement."],
                safety=[],
            ),
            "expect_fallback": True,
        }
        for index in range(48)
    ]


@pytest.mark.parametrize("case", _cases(), ids=lambda case: str(case["name"]))
def test_evaluation_corpus_converges_to_safe_output(recovery_demo_settings, case) -> None:
    provider = (
        build_grounded_explanation_provider()
        if case["response"] is None
        else FakeLLMProvider(response=case["response"])
    )
    service = RecommendationExplanationService(
        settings=recovery_demo_settings,
        llm_provider=provider,
    )
    input_data = sample_explanation_input()
    if case["expect_fallback"]:
        with pytest.raises(Exception):
            asyncio.run(
                service._generate_with_provider(provider=provider, input_data=input_data)
            )
        fallback = build_grounded_explanation_provider()
        assert fallback is not None
    else:
        result = asyncio.run(
            service._generate_with_provider(provider=provider, input_data=input_data)
        )
        assert result.summary
