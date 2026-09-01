"""Candidate generation tests."""

from __future__ import annotations

import pytest

from app.domain.enums import CaseType, FailureCategory, RecoveryActionType
from app.recovery.candidates import generate_candidates
from app.recovery.schemas import CandidateGenerationContext

MATRIX_CASES: list[tuple[FailureCategory, tuple[RecoveryActionType, ...]]] = [
    (
        FailureCategory.PAYMENT_RAIL_DOWNTIME,
        (
            RecoveryActionType.WAIT,
            RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD,
            RecoveryActionType.CREATE_PAYMENT_LINK,
            RecoveryActionType.STOP,
        ),
    ),
    (
        FailureCategory.INSUFFICIENT_FUNDS,
        (
            RecoveryActionType.WAIT,
            RecoveryActionType.SEND_RECOVERY_MESSAGE,
            RecoveryActionType.CREATE_PAYMENT_LINK,
            RecoveryActionType.STOP,
        ),
    ),
    (
        FailureCategory.AUTHENTICATION_FAILURE,
        (
            RecoveryActionType.RETRY_SAME_METHOD,
            RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD,
            RecoveryActionType.CREATE_PAYMENT_LINK,
            RecoveryActionType.STOP,
        ),
    ),
    (
        FailureCategory.BANK_OR_ISSUER_DECLINE,
        (
            RecoveryActionType.WAIT,
            RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD,
            RecoveryActionType.CREATE_PAYMENT_LINK,
            RecoveryActionType.STOP,
        ),
    ),
    (
        FailureCategory.EXPIRED_OR_INVALID_METHOD,
        (
            RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD,
            RecoveryActionType.CREATE_PAYMENT_LINK,
            RecoveryActionType.SEND_RECOVERY_MESSAGE,
            RecoveryActionType.STOP,
        ),
    ),
    (
        FailureCategory.TECHNICAL_FAILURE,
        (
            RecoveryActionType.WAIT,
            RecoveryActionType.RETRY_SAME_METHOD,
            RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD,
            RecoveryActionType.STOP,
        ),
    ),
]


@pytest.mark.parametrize(("category", "expected"), MATRIX_CASES)
def test_failure_category_candidate_matrix(
    category: FailureCategory,
    expected: tuple[RecoveryActionType, ...],
) -> None:
    result = generate_candidates(
        CandidateGenerationContext(
            failure_category=category,
            case_type=CaseType.PAYMENT_FAILURE,
        )
    )
    assert result == expected
    assert RecoveryActionType.STOP in result


def test_unknown_without_payment_link_data() -> None:
    result = generate_candidates(
        CandidateGenerationContext(
            failure_category=FailureCategory.UNKNOWN,
            case_type=CaseType.PAYMENT_FAILURE,
            payment_link_data_sufficient=False,
        )
    )
    assert result == (
        RecoveryActionType.WAIT,
        RecoveryActionType.ESCALATE_TO_HUMAN,
        RecoveryActionType.STOP,
    )


def test_unknown_with_payment_link_data() -> None:
    result = generate_candidates(
        CandidateGenerationContext(
            failure_category=FailureCategory.UNKNOWN,
            case_type=CaseType.PAYMENT_FAILURE,
            payment_link_data_sufficient=True,
        )
    )
    assert result == (
        RecoveryActionType.WAIT,
        RecoveryActionType.ESCALATE_TO_HUMAN,
        RecoveryActionType.CREATE_PAYMENT_LINK,
        RecoveryActionType.STOP,
    )


def test_subscription_pending_with_retries_excludes_retry_same_method() -> None:
    result = generate_candidates(
        CandidateGenerationContext(
            failure_category=FailureCategory.MANDATE_OR_RECURRING_FAILURE,
            case_type=CaseType.SUBSCRIPTION_FAILURE,
            subscription_status="pending",
            provider_retries_active=True,
        )
    )
    assert RecoveryActionType.RETRY_SAME_METHOD not in result
    assert result == (
        RecoveryActionType.WAIT,
        RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD,
        RecoveryActionType.SEND_RECOVERY_MESSAGE,
        RecoveryActionType.STOP,
    )


def test_subscription_halted_matrix() -> None:
    result = generate_candidates(
        CandidateGenerationContext(
            failure_category=FailureCategory.MANDATE_OR_RECURRING_FAILURE,
            case_type=CaseType.SUBSCRIPTION_FAILURE,
            subscription_status="halted",
        )
    )
    assert result == (
        RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD,
        RecoveryActionType.CREATE_PAYMENT_LINK,
        RecoveryActionType.ESCALATE_TO_HUMAN,
        RecoveryActionType.STOP,
    )


def test_uncertain_provider_state_excludes_retry_same_method() -> None:
    result = generate_candidates(
        CandidateGenerationContext(
            failure_category=FailureCategory.AUTHENTICATION_FAILURE,
            case_type=CaseType.PAYMENT_FAILURE,
            uncertain_provider_state=True,
        )
    )
    assert RecoveryActionType.RETRY_SAME_METHOD not in result


def test_active_downtime_excludes_retry_same_method() -> None:
    result = generate_candidates(
        CandidateGenerationContext(
            failure_category=FailureCategory.AUTHENTICATION_FAILURE,
            case_type=CaseType.PAYMENT_FAILURE,
            active_payment_rail_downtime=True,
        )
    )
    assert RecoveryActionType.RETRY_SAME_METHOD not in result
    assert result == (
        RecoveryActionType.WAIT,
        RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD,
        RecoveryActionType.CREATE_PAYMENT_LINK,
        RecoveryActionType.STOP,
    )


def test_candidate_generation_is_deterministic() -> None:
    context = CandidateGenerationContext(
        failure_category=FailureCategory.INSUFFICIENT_FUNDS,
        case_type=CaseType.PAYMENT_FAILURE,
    )
    first = generate_candidates(context)
    second = generate_candidates(context)
    assert first == second
