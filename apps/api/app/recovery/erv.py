"""Expected Recovery Value calculations."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.domain.enums import RecoveryActionType
from app.recovery.schemas import ERVBreakdown

_BPS_DENOMINATOR = Decimal("10000")

# P0 decision-engine coefficients; not claimed real-world financial estimates.
ACTION_COST_MINOR: dict[RecoveryActionType, int] = {
    RecoveryActionType.WAIT: 0,
    RecoveryActionType.RETRY_SAME_METHOD: 100,
    RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD: 200,
    RecoveryActionType.CREATE_PAYMENT_LINK: 300,
    RecoveryActionType.SEND_RECOVERY_MESSAGE: 500,
    RecoveryActionType.ESCALATE_TO_HUMAN: 800,
    RecoveryActionType.STOP: 0,
}

OPERATIONAL_RISK_BPS: dict[RecoveryActionType, int] = {
    RecoveryActionType.WAIT: 5,
    RecoveryActionType.RETRY_SAME_METHOD: 20,
    RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD: 15,
    RecoveryActionType.CREATE_PAYMENT_LINK: 25,
    RecoveryActionType.SEND_RECOVERY_MESSAGE: 30,
    RecoveryActionType.ESCALATE_TO_HUMAN: 40,
    RecoveryActionType.STOP: 0,
}

DELAY_HOURS: dict[RecoveryActionType, Decimal] = {
    RecoveryActionType.WAIT: Decimal("4"),
    RecoveryActionType.RETRY_SAME_METHOD: Decimal("0"),
    RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD: Decimal("0"),
    RecoveryActionType.CREATE_PAYMENT_LINK: Decimal("0"),
    RecoveryActionType.SEND_RECOVERY_MESSAGE: Decimal("0"),
    RecoveryActionType.ESCALATE_TO_HUMAN: Decimal("0"),
    RecoveryActionType.STOP: Decimal("0"),
}

DELAY_PENALTY_BPS_PER_HOUR = 2
BASE_CONTACT_PENALTY_MINOR = 250

# P0 configuration: customer-contact actions for fatigue and contact-cap policy.
CONTACT_ACTION_TYPES: frozenset[RecoveryActionType] = frozenset(
    {
        RecoveryActionType.SEND_RECOVERY_MESSAGE,
    }
)


def round_half_up(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _validate_probability(probability: Decimal) -> Decimal:
    if not Decimal("0") <= probability <= Decimal("1"):
        raise ValueError("success_probability must be within [0, 1].")
    return probability


def _validate_amount(amount_at_risk_minor: int) -> int:
    if amount_at_risk_minor < 0:
        raise ValueError("amount_at_risk_minor must be non-negative.")
    return amount_at_risk_minor


def calculate_fatigue_penalty(
    *,
    action: RecoveryActionType,
    contacts_last_24h: int,
) -> int:
    if action not in CONTACT_ACTION_TYPES:
        return 0
    if contacts_last_24h < 0:
        raise ValueError("contacts_last_24h must be non-negative.")
    return BASE_CONTACT_PENALTY_MINOR * (1 + contacts_last_24h)


def calculate_operational_risk_penalty(
    *,
    action: RecoveryActionType,
    amount_at_risk_minor: int,
) -> int:
    amount = _validate_amount(amount_at_risk_minor)
    risk_bps = OPERATIONAL_RISK_BPS[action]
    if risk_bps < 0:
        raise ValueError("risk basis points must be non-negative.")
    return round_half_up(Decimal(amount) * Decimal(risk_bps) / _BPS_DENOMINATOR)


def calculate_delay_penalty(
    *,
    action: RecoveryActionType,
    amount_at_risk_minor: int,
) -> int:
    amount = _validate_amount(amount_at_risk_minor)
    delay_hours = DELAY_HOURS[action]
    return round_half_up(
        Decimal(amount) * delay_hours * Decimal(DELAY_PENALTY_BPS_PER_HOUR) / _BPS_DENOMINATOR
    )


def calculate_erv(
    *,
    action: RecoveryActionType,
    amount_at_risk_minor: int,
    success_probability: Decimal,
    contacts_last_24h: int = 0,
) -> ERVBreakdown:
    _validate_amount(amount_at_risk_minor)
    probability = _validate_probability(success_probability)

    if action == RecoveryActionType.STOP:
        return ERVBreakdown(
            success_probability=Decimal("0"),
            expected_recovered_minor=0,
            action_cost_minor=0,
            fatigue_penalty_minor=0,
            operational_risk_penalty_minor=0,
            delay_penalty_minor=0,
            expected_value_minor=0,
        )

    expected_recovered = round_half_up(Decimal(amount_at_risk_minor) * probability)
    action_cost = ACTION_COST_MINOR[action]
    fatigue = calculate_fatigue_penalty(
        action=action,
        contacts_last_24h=contacts_last_24h,
    )
    operational_risk = calculate_operational_risk_penalty(
        action=action,
        amount_at_risk_minor=amount_at_risk_minor,
    )
    delay_penalty = calculate_delay_penalty(
        action=action,
        amount_at_risk_minor=amount_at_risk_minor,
    )

    expected_value = (
        expected_recovered - action_cost - fatigue - operational_risk - delay_penalty
    )

    return ERVBreakdown(
        success_probability=probability,
        expected_recovered_minor=expected_recovered,
        action_cost_minor=action_cost,
        fatigue_penalty_minor=fatigue,
        operational_risk_penalty_minor=operational_risk,
        delay_penalty_minor=delay_penalty,
        expected_value_minor=expected_value,
    )
