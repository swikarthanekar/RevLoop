"""Confidence heuristic tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.recovery.confidence import calculate_confidence, calculate_prediction_certainty


def test_prediction_certainty_at_half_is_zero() -> None:
    assert calculate_prediction_certainty(Decimal("0.5")) == Decimal("0")


@pytest.mark.parametrize("probability", [Decimal("0"), Decimal("1")])
def test_prediction_certainty_at_extremes_is_one(probability: Decimal) -> None:
    assert calculate_prediction_certainty(probability) == Decimal("1")


def test_confidence_exact_weighted_result() -> None:
    confidence = calculate_confidence(
        feature_completeness=Decimal("1"),
        success_probability=Decimal("1"),
        evidence_strength=Decimal("1"),
    )
    assert confidence == Decimal("1")


def test_confidence_input_boundaries_are_clamped() -> None:
    confidence = calculate_confidence(
        feature_completeness=Decimal("2"),
        success_probability=Decimal("-0.2"),
        evidence_strength=Decimal("3"),
    )
    assert Decimal("0") <= confidence <= Decimal("1")


def test_confidence_is_deterministic() -> None:
    kwargs = {
        "feature_completeness": Decimal("0.8"),
        "success_probability": Decimal("0.72"),
        "evidence_strength": Decimal("0.65"),
    }
    assert calculate_confidence(**kwargs) == calculate_confidence(**kwargs)
