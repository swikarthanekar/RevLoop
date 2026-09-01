"""ERV calculation tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.enums import RecoveryActionType
from app.recovery.erv import (
    calculate_delay_penalty,
    calculate_erv,
    calculate_fatigue_penalty,
    calculate_operational_risk_penalty,
    round_half_up,
)


def test_round_half_up_boundary_values() -> None:
    assert round_half_up(Decimal("10.4")) == 10
    assert round_half_up(Decimal("10.5")) == 11
    assert round_half_up(Decimal("10.6")) == 11


def test_expected_recovered_uses_round_half_up() -> None:
    breakdown = calculate_erv(
        action=RecoveryActionType.WAIT,
        amount_at_risk_minor=1001,
        success_probability=Decimal("0.5"),
    )
    assert breakdown.expected_recovered_minor == 501


def test_erv_decomposition_is_exact() -> None:
    breakdown = calculate_erv(
        action=RecoveryActionType.SEND_RECOVERY_MESSAGE,
        amount_at_risk_minor=100_000,
        success_probability=Decimal("0.60"),
        contacts_last_24h=1,
    )
    expected_value = (
        breakdown.expected_recovered_minor
        - breakdown.action_cost_minor
        - breakdown.fatigue_penalty_minor
        - breakdown.operational_risk_penalty_minor
        - breakdown.delay_penalty_minor
    )
    assert breakdown.expected_value_minor == expected_value


def test_operational_risk_round_half_up() -> None:
    penalty = calculate_operational_risk_penalty(
        action=RecoveryActionType.CREATE_PAYMENT_LINK,
        amount_at_risk_minor=10_001,
    )
    assert penalty == round_half_up(Decimal("10001") * Decimal("25") / Decimal("10000"))


def test_delay_penalty_round_half_up() -> None:
    penalty = calculate_delay_penalty(
        action=RecoveryActionType.WAIT,
        amount_at_risk_minor=10_001,
    )
    assert penalty == round_half_up(
        Decimal("10001") * Decimal("4") * Decimal("2") / Decimal("10000")
    )


def test_fatigue_penalty_progression() -> None:
    first = calculate_fatigue_penalty(
        action=RecoveryActionType.SEND_RECOVERY_MESSAGE,
        contacts_last_24h=0,
    )
    second = calculate_fatigue_penalty(
        action=RecoveryActionType.SEND_RECOVERY_MESSAGE,
        contacts_last_24h=1,
    )
    assert second == first * 2
    assert calculate_fatigue_penalty(
        action=RecoveryActionType.WAIT,
        contacts_last_24h=5,
    ) == 0


def test_negative_erv_is_preserved() -> None:
    breakdown = calculate_erv(
        action=RecoveryActionType.ESCALATE_TO_HUMAN,
        amount_at_risk_minor=100,
        success_probability=Decimal("0.05"),
    )
    assert breakdown.expected_value_minor < 0


def test_stop_is_exactly_zero() -> None:
    breakdown = calculate_erv(
        action=RecoveryActionType.STOP,
        amount_at_risk_minor=999_999,
        success_probability=Decimal("0.99"),
        contacts_last_24h=10,
    )
    assert breakdown.success_probability == Decimal("0")
    assert breakdown.expected_recovered_minor == 0
    assert breakdown.expected_value_minor == 0
    assert breakdown.action_cost_minor == 0
    assert breakdown.fatigue_penalty_minor == 0
    assert breakdown.operational_risk_penalty_minor == 0
    assert breakdown.delay_penalty_minor == 0


def test_invalid_probability_rejected() -> None:
    with pytest.raises(ValueError):
        calculate_erv(
            action=RecoveryActionType.WAIT,
            amount_at_risk_minor=1000,
            success_probability=Decimal("1.1"),
        )
