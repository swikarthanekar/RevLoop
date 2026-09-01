"""Deterministic heuristic fallback propensity probabilities.

These values are a versioned P0 demo baseline, not statistically trained probabilities.
"""

from __future__ import annotations

from decimal import Decimal

from app.domain.enums import CaseType, FailureCategory, RecoveryActionType
from app.recovery.candidates import (
    FAILURE_CATEGORY_MATRIX,
    EffectiveScenarioKind,
    resolve_effective_scenario,
)
from app.recovery.schemas import CandidateGenerationContext

FALLBACK_MODEL_VERSION = "heuristic_fallback_v1"

_ZERO = Decimal("0")
_ONE = Decimal("1")

_ACTIVE_DOWNTIME_PROBABILITIES: dict[RecoveryActionType, Decimal] = {
    RecoveryActionType.WAIT: Decimal("0.60"),
    RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD: Decimal("0.72"),
    RecoveryActionType.CREATE_PAYMENT_LINK: Decimal("0.65"),
    RecoveryActionType.STOP: _ZERO,
}

_BASE_BY_CATEGORY: dict[FailureCategory, dict[RecoveryActionType, Decimal]] = {
    FailureCategory.PAYMENT_RAIL_DOWNTIME: _ACTIVE_DOWNTIME_PROBABILITIES,
    FailureCategory.INSUFFICIENT_FUNDS: {
        RecoveryActionType.WAIT: Decimal("0.55"),
        RecoveryActionType.SEND_RECOVERY_MESSAGE: Decimal("0.48"),
        RecoveryActionType.CREATE_PAYMENT_LINK: Decimal("0.62"),
        RecoveryActionType.STOP: _ZERO,
    },
    FailureCategory.AUTHENTICATION_FAILURE: {
        RecoveryActionType.RETRY_SAME_METHOD: Decimal("0.58"),
        RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD: Decimal("0.66"),
        RecoveryActionType.CREATE_PAYMENT_LINK: Decimal("0.61"),
        RecoveryActionType.STOP: _ZERO,
    },
    FailureCategory.BANK_OR_ISSUER_DECLINE: {
        RecoveryActionType.WAIT: Decimal("0.52"),
        RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD: Decimal("0.64"),
        RecoveryActionType.CREATE_PAYMENT_LINK: Decimal("0.59"),
        RecoveryActionType.STOP: _ZERO,
    },
    FailureCategory.EXPIRED_OR_INVALID_METHOD: {
        RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD: Decimal("0.70"),
        RecoveryActionType.CREATE_PAYMENT_LINK: Decimal("0.68"),
        RecoveryActionType.SEND_RECOVERY_MESSAGE: Decimal("0.45"),
        RecoveryActionType.STOP: _ZERO,
    },
    FailureCategory.TECHNICAL_FAILURE: {
        RecoveryActionType.WAIT: Decimal("0.57"),
        RecoveryActionType.RETRY_SAME_METHOD: Decimal("0.50"),
        RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD: Decimal("0.63"),
        RecoveryActionType.STOP: _ZERO,
    },
    FailureCategory.UNKNOWN: {
        RecoveryActionType.WAIT: Decimal("0.35"),
        RecoveryActionType.ESCALATE_TO_HUMAN: Decimal("0.40"),
        RecoveryActionType.CREATE_PAYMENT_LINK: Decimal("0.42"),
        RecoveryActionType.STOP: _ZERO,
    },
    FailureCategory.MANDATE_OR_RECURRING_FAILURE: {
        RecoveryActionType.WAIT: Decimal("0.50"),
        RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD: Decimal("0.58"),
        RecoveryActionType.SEND_RECOVERY_MESSAGE: Decimal("0.46"),
        RecoveryActionType.STOP: _ZERO,
    },
    FailureCategory.CUSTOMER_ABANDONMENT: {
        RecoveryActionType.WAIT: Decimal("0.30"),
        RecoveryActionType.ESCALATE_TO_HUMAN: Decimal("0.38"),
        RecoveryActionType.CREATE_PAYMENT_LINK: Decimal("0.40"),
        RecoveryActionType.STOP: _ZERO,
    },
}

_SCENARIO_PROBABILITIES: dict[EffectiveScenarioKind, dict[RecoveryActionType, Decimal]] = {
    EffectiveScenarioKind.ACTIVE_DOWNTIME: _ACTIVE_DOWNTIME_PROBABILITIES,
    EffectiveScenarioKind.SUBSCRIPTION_PENDING_RETRIES: {
        RecoveryActionType.WAIT: Decimal("0.62"),
        RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD: Decimal("0.67"),
        RecoveryActionType.SEND_RECOVERY_MESSAGE: Decimal("0.49"),
        RecoveryActionType.STOP: _ZERO,
    },
    EffectiveScenarioKind.SUBSCRIPTION_HALTED: {
        RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD: Decimal("0.55"),
        RecoveryActionType.CREATE_PAYMENT_LINK: Decimal("0.60"),
        RecoveryActionType.ESCALATE_TO_HUMAN: Decimal("0.44"),
        RecoveryActionType.STOP: _ZERO,
    },
    EffectiveScenarioKind.SUBSCRIPTION_CONSERVATIVE: {
        RecoveryActionType.WAIT: Decimal("0.50"),
        RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD: Decimal("0.58"),
        RecoveryActionType.SEND_RECOVERY_MESSAGE: Decimal("0.46"),
        RecoveryActionType.STOP: _ZERO,
    },
}


def _probability_table_for_context(
    context: CandidateGenerationContext,
) -> dict[RecoveryActionType, Decimal]:
    scenario = resolve_effective_scenario(context)
    if scenario.kind in _SCENARIO_PROBABILITIES:
        return _SCENARIO_PROBABILITIES[scenario.kind]

    if scenario.kind == EffectiveScenarioKind.UNKNOWN:
        table = dict(_BASE_BY_CATEGORY[FailureCategory.UNKNOWN])
        if not scenario.payment_link_data_sufficient:
            table.pop(RecoveryActionType.CREATE_PAYMENT_LINK, None)
        return table

    assert scenario.failure_category is not None
    return _BASE_BY_CATEGORY[scenario.failure_category]


def get_fallback_probability(
    context: CandidateGenerationContext,
    action: RecoveryActionType,
) -> Decimal:
    if action == RecoveryActionType.STOP:
        return _ZERO

    table = _probability_table_for_context(context)
    if action not in table:
        effective = resolve_effective_scenario(context)
        raise KeyError(
            f"No fallback probability configured for action={action.value} "
            f"effective_scenario={effective.kind.value} "
            f"failure_category={context.failure_category.value} "
            f"model_version={FALLBACK_MODEL_VERSION}"
        )

    probability = table[action]
    if not _ZERO <= probability <= _ONE:
        raise ValueError("Fallback probabilities must be within [0, 1].")
    return probability


def iter_supported_candidate_contexts() -> tuple[CandidateGenerationContext, ...]:
    """Supported generation contexts for fallback completeness tests."""
    scenarios: list[CandidateGenerationContext] = []

    for category in FAILURE_CATEGORY_MATRIX:
        scenarios.append(
            CandidateGenerationContext(
                failure_category=category,
                case_type=CaseType.PAYMENT_FAILURE,
            )
        )
        scenarios.append(
            CandidateGenerationContext(
                failure_category=category,
                case_type=CaseType.PAYMENT_FAILURE,
                active_payment_rail_downtime=True,
            )
        )

    scenarios.extend(
        [
            CandidateGenerationContext(
                failure_category=FailureCategory.UNKNOWN,
                case_type=CaseType.PAYMENT_FAILURE,
            ),
            CandidateGenerationContext(
                failure_category=FailureCategory.UNKNOWN,
                case_type=CaseType.PAYMENT_FAILURE,
                payment_link_data_sufficient=True,
            ),
            CandidateGenerationContext(
                failure_category=FailureCategory.MANDATE_OR_RECURRING_FAILURE,
                case_type=CaseType.SUBSCRIPTION_FAILURE,
                subscription_status="pending",
                provider_retries_active=True,
            ),
            CandidateGenerationContext(
                failure_category=FailureCategory.MANDATE_OR_RECURRING_FAILURE,
                case_type=CaseType.SUBSCRIPTION_FAILURE,
                subscription_status="pending",
                provider_retries_active=True,
                active_payment_rail_downtime=True,
            ),
            CandidateGenerationContext(
                failure_category=FailureCategory.MANDATE_OR_RECURRING_FAILURE,
                case_type=CaseType.SUBSCRIPTION_FAILURE,
                subscription_status="halted",
            ),
            CandidateGenerationContext(
                failure_category=FailureCategory.MANDATE_OR_RECURRING_FAILURE,
                case_type=CaseType.SUBSCRIPTION_FAILURE,
                subscription_status="halted",
                active_payment_rail_downtime=True,
            ),
            CandidateGenerationContext(
                failure_category=FailureCategory.TECHNICAL_FAILURE,
                case_type=CaseType.SUBSCRIPTION_FAILURE,
                subscription_status="active",
            ),
            CandidateGenerationContext(
                failure_category=FailureCategory.AUTHENTICATION_FAILURE,
                case_type=CaseType.SUBSCRIPTION_FAILURE,
                subscription_status="active",
            ),
        ]
    )
    return tuple(scenarios)


def iter_documented_candidate_scenarios() -> tuple[CandidateGenerationContext, ...]:
    return iter_supported_candidate_contexts()
