"""Fallback probability tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.enums import RecoveryActionType
from app.ml.fallback import (
    FALLBACK_MODEL_VERSION,
    get_fallback_probability,
    iter_supported_candidate_contexts,
)
from app.recovery.candidates import generate_candidates


def test_fallback_model_version_is_stable() -> None:
    assert FALLBACK_MODEL_VERSION == "heuristic_fallback_v1"


def test_stop_probability_is_exactly_zero() -> None:
    for scenario in iter_supported_candidate_contexts():
        assert get_fallback_probability(scenario, RecoveryActionType.STOP) == Decimal("0")


def test_all_generated_candidates_have_fallback_probabilities() -> None:
    for scenario in iter_supported_candidate_contexts():
        for action in generate_candidates(scenario):
            probability = get_fallback_probability(scenario, action)
            assert isinstance(probability, Decimal)
            assert Decimal("0") <= probability <= Decimal("1")


def test_missing_fallback_configuration_raises() -> None:
    scenario = iter_supported_candidate_contexts()[0]
    with pytest.raises(KeyError):
        get_fallback_probability(scenario, RecoveryActionType.ESCALATE_TO_HUMAN)


def test_fallback_probabilities_are_deterministic() -> None:
    scenario = iter_supported_candidate_contexts()[0]
    action = generate_candidates(scenario)[0]
    first = get_fallback_probability(scenario, action)
    second = get_fallback_probability(scenario, action)
    assert first == second
