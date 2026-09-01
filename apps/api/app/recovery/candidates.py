"""Deterministic candidate action generation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.domain.enums import CaseType, FailureCategory, RecoveryActionType
from app.recovery.schemas import CandidateGenerationContext

ACTION_PRIORITY: tuple[RecoveryActionType, ...] = (
    RecoveryActionType.WAIT,
    RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD,
    RecoveryActionType.CREATE_PAYMENT_LINK,
    RecoveryActionType.RETRY_SAME_METHOD,
    RecoveryActionType.SEND_RECOVERY_MESSAGE,
    RecoveryActionType.ESCALATE_TO_HUMAN,
    RecoveryActionType.STOP,
)

ACTIVE_DOWNTIME_MATRIX: tuple[RecoveryActionType, ...] = (
    RecoveryActionType.WAIT,
    RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD,
    RecoveryActionType.CREATE_PAYMENT_LINK,
    RecoveryActionType.STOP,
)

FAILURE_CATEGORY_MATRIX: dict[FailureCategory, tuple[RecoveryActionType, ...]] = {
    FailureCategory.PAYMENT_RAIL_DOWNTIME: ACTIVE_DOWNTIME_MATRIX,
    FailureCategory.INSUFFICIENT_FUNDS: (
        RecoveryActionType.WAIT,
        RecoveryActionType.SEND_RECOVERY_MESSAGE,
        RecoveryActionType.CREATE_PAYMENT_LINK,
        RecoveryActionType.STOP,
    ),
    FailureCategory.AUTHENTICATION_FAILURE: (
        RecoveryActionType.RETRY_SAME_METHOD,
        RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD,
        RecoveryActionType.CREATE_PAYMENT_LINK,
        RecoveryActionType.STOP,
    ),
    FailureCategory.BANK_OR_ISSUER_DECLINE: (
        RecoveryActionType.WAIT,
        RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD,
        RecoveryActionType.CREATE_PAYMENT_LINK,
        RecoveryActionType.STOP,
    ),
    FailureCategory.EXPIRED_OR_INVALID_METHOD: (
        RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD,
        RecoveryActionType.CREATE_PAYMENT_LINK,
        RecoveryActionType.SEND_RECOVERY_MESSAGE,
        RecoveryActionType.STOP,
    ),
    FailureCategory.TECHNICAL_FAILURE: (
        RecoveryActionType.WAIT,
        RecoveryActionType.RETRY_SAME_METHOD,
        RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD,
        RecoveryActionType.STOP,
    ),
}

SUBSCRIPTION_PENDING_RETRIES_MATRIX: tuple[RecoveryActionType, ...] = (
    RecoveryActionType.WAIT,
    RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD,
    RecoveryActionType.SEND_RECOVERY_MESSAGE,
    RecoveryActionType.STOP,
)

SUBSCRIPTION_HALTED_MATRIX: tuple[RecoveryActionType, ...] = (
    RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD,
    RecoveryActionType.CREATE_PAYMENT_LINK,
    RecoveryActionType.ESCALATE_TO_HUMAN,
    RecoveryActionType.STOP,
)

UNKNOWN_MATRIX_BASE: tuple[RecoveryActionType, ...] = (
    RecoveryActionType.WAIT,
    RecoveryActionType.ESCALATE_TO_HUMAN,
    RecoveryActionType.STOP,
)

CONSERVATIVE_RECURRING_FALLBACK_MATRIX: tuple[RecoveryActionType, ...] = (
    RecoveryActionType.WAIT,
    RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD,
    RecoveryActionType.SEND_RECOVERY_MESSAGE,
    RecoveryActionType.STOP,
)


class EffectiveScenarioKind(str, Enum):
    ACTIVE_DOWNTIME = "active_downtime"
    SUBSCRIPTION_HALTED = "subscription_halted"
    SUBSCRIPTION_PENDING_RETRIES = "subscription_pending_retries"
    SUBSCRIPTION_CONSERVATIVE = "subscription_conservative"
    FAILURE_CATEGORY = "failure_category"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class EffectiveScenario:
    kind: EffectiveScenarioKind
    failure_category: FailureCategory | None = None
    payment_link_data_sufficient: bool = False


def _normalize_subscription_status(status: str | None) -> str | None:
    if status is None:
        return None
    normalized = status.strip().lower()
    return normalized or None


def resolve_effective_scenario(context: CandidateGenerationContext) -> EffectiveScenario:
    if context.active_payment_rail_downtime:
        return EffectiveScenario(kind=EffectiveScenarioKind.ACTIVE_DOWNTIME)

    if context.case_type == CaseType.SUBSCRIPTION_FAILURE:
        subscription_status = _normalize_subscription_status(context.subscription_status)
        if subscription_status == "halted":
            return EffectiveScenario(kind=EffectiveScenarioKind.SUBSCRIPTION_HALTED)
        if subscription_status == "pending" and context.provider_retries_active:
            return EffectiveScenario(kind=EffectiveScenarioKind.SUBSCRIPTION_PENDING_RETRIES)
        return EffectiveScenario(kind=EffectiveScenarioKind.SUBSCRIPTION_CONSERVATIVE)

    if context.failure_category == FailureCategory.UNKNOWN:
        return EffectiveScenario(
            kind=EffectiveScenarioKind.UNKNOWN,
            payment_link_data_sufficient=context.payment_link_data_sufficient,
        )

    if context.failure_category in FAILURE_CATEGORY_MATRIX:
        return EffectiveScenario(
            kind=EffectiveScenarioKind.FAILURE_CATEGORY,
            failure_category=context.failure_category,
        )

    return EffectiveScenario(
        kind=EffectiveScenarioKind.UNKNOWN,
        payment_link_data_sufficient=context.payment_link_data_sufficient,
    )


def _matrix_for_scenario(scenario: EffectiveScenario) -> tuple[RecoveryActionType, ...]:
    if scenario.kind == EffectiveScenarioKind.ACTIVE_DOWNTIME:
        return ACTIVE_DOWNTIME_MATRIX

    if scenario.kind == EffectiveScenarioKind.SUBSCRIPTION_HALTED:
        return SUBSCRIPTION_HALTED_MATRIX

    if scenario.kind == EffectiveScenarioKind.SUBSCRIPTION_PENDING_RETRIES:
        return SUBSCRIPTION_PENDING_RETRIES_MATRIX

    if scenario.kind == EffectiveScenarioKind.SUBSCRIPTION_CONSERVATIVE:
        return CONSERVATIVE_RECURRING_FALLBACK_MATRIX

    if scenario.kind == EffectiveScenarioKind.UNKNOWN:
        actions = list(UNKNOWN_MATRIX_BASE)
        if scenario.payment_link_data_sufficient:
            actions.insert(2, RecoveryActionType.CREATE_PAYMENT_LINK)
        return tuple(actions)

    assert scenario.failure_category is not None
    return FAILURE_CATEGORY_MATRIX[scenario.failure_category]


def _retry_same_method_blocked(context: CandidateGenerationContext) -> bool:
    if context.active_payment_rail_downtime:
        return True
    if context.failure_category == FailureCategory.PAYMENT_RAIL_DOWNTIME:
        return True
    if context.uncertain_provider_state:
        return True
    if (
        context.case_type == CaseType.SUBSCRIPTION_FAILURE
        and _normalize_subscription_status(context.subscription_status) == "pending"
        and context.provider_retries_active
    ):
        return True
    return False


def validate_candidate_generation_context(context: CandidateGenerationContext) -> None:
    if context.case_type != CaseType.PAYMENT_FAILURE:
        return
    if context.subscription_status is not None:
        raise ValueError("subscription_status is only valid for SUBSCRIPTION_FAILURE cases.")
    if context.provider_retries_active:
        raise ValueError("provider_retries_active is only valid for SUBSCRIPTION_FAILURE cases.")


def generate_candidates(context: CandidateGenerationContext) -> tuple[RecoveryActionType, ...]:
    """Return deterministic ordered candidate actions for analyzable cases."""
    validate_candidate_generation_context(context)
    base_actions = _matrix_for_scenario(resolve_effective_scenario(context))
    block_retry = _retry_same_method_blocked(context)

    filtered: list[RecoveryActionType] = []
    for action in base_actions:
        if action == RecoveryActionType.RETRY_SAME_METHOD and block_retry:
            continue
        filtered.append(action)

    if RecoveryActionType.STOP not in filtered:
        filtered.append(RecoveryActionType.STOP)

    return tuple(filtered)
