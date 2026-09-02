"""Deterministic formatting helpers for grounded LLM validation."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.domain.enums import RecoveryActionType


def format_minor_amount(amount_minor: int, currency: str) -> str:
    major = (Decimal(amount_minor) / Decimal(100)).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )
    return f"{currency.upper()} {major}"


def format_probability_percent(probability: Decimal) -> str:
    pct = (probability * Decimal(100)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    normalized = pct.normalize()
    return f"{normalized}%"


def format_confidence_percent(confidence: Decimal) -> str:
    return format_probability_percent(confidence)


def action_label(action_type: str) -> str:
    try:
        action = RecoveryActionType(action_type)
    except ValueError:
        return action_type.replace("_", " ").title()
    labels = {
        RecoveryActionType.WAIT: "Wait and retry later",
        RecoveryActionType.RETRY_SAME_METHOD: "Retry the same payment method",
        RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD: "Request an alternate payment method",
        RecoveryActionType.CREATE_PAYMENT_LINK: "Create a payment link",
        RecoveryActionType.SEND_RECOVERY_MESSAGE: "Send a recovery message",
        RecoveryActionType.ESCALATE_TO_HUMAN: "Escalate to a human agent",
        RecoveryActionType.STOP: "Stop recovery",
    }
    return labels.get(action, action.value.replace("_", " ").title())


def other_action_labels(selected_action: str) -> list[str]:
    labels: list[str] = []
    for action in RecoveryActionType:
        if action.value == selected_action:
            continue
        labels.append(action_label(action.value))
        labels.append(action.value.replace("_", " ").lower())
    return labels
