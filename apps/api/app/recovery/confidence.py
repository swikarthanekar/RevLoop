"""Confidence heuristic for recovery recommendations."""

from __future__ import annotations

from decimal import Decimal

_WEIGHT_FEATURE_COMPLETENESS = Decimal("0.45")
_WEIGHT_PREDICTION_CERTAINTY = Decimal("0.35")
_WEIGHT_EVIDENCE_STRENGTH = Decimal("0.20")
_HALF = Decimal("0.5")
_ZERO = Decimal("0")
_ONE = Decimal("1")


def _clamp_unit(value: Decimal) -> Decimal:
    if value < _ZERO:
        return _ZERO
    if value > _ONE:
        return _ONE
    return value


def _to_decimal(value: float | Decimal) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def calculate_prediction_certainty(success_probability: Decimal) -> Decimal:
    probability = _clamp_unit(_to_decimal(success_probability))
    return _clamp_unit(Decimal("2") * (probability - _HALF).copy_abs())


def calculate_confidence(
    *,
    feature_completeness: float | Decimal,
    success_probability: Decimal,
    evidence_strength: float | Decimal,
) -> Decimal:
    completeness = _clamp_unit(_to_decimal(feature_completeness))
    evidence = _clamp_unit(_to_decimal(evidence_strength))
    probability = _clamp_unit(_to_decimal(success_probability))

    prediction_certainty = _clamp_unit(Decimal("2") * (probability - _HALF).copy_abs())

    confidence = (
        _WEIGHT_FEATURE_COMPLETENESS * completeness
        + _WEIGHT_PREDICTION_CERTAINTY * prediction_certainty
        + _WEIGHT_EVIDENCE_STRENGTH * evidence
    )
    return _clamp_unit(confidence)
