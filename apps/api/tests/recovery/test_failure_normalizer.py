"""Failure normalization tests."""

from __future__ import annotations

import pytest

from app.domain.enums import FailureCategory
from app.recovery.failure_normalizer import (
    ERROR_REASON_MAP,
    normalize_payment_failure,
    normalize_subscription_failure,
)
from app.recovery.schemas import (
    DowntimeContext,
    PaymentFailureEvidence,
    SubscriptionFailureEvidence,
)


@pytest.mark.parametrize(
    ("error_reason", "expected"),
    [
        ("payment_rail_unavailable", FailureCategory.PAYMENT_RAIL_DOWNTIME),
        ("insufficient_funds", FailureCategory.INSUFFICIENT_FUNDS),
        ("payment_authentication_failure", FailureCategory.AUTHENTICATION_FAILURE),
        ("bank_declined", FailureCategory.BANK_OR_ISSUER_DECLINE),
        ("expired_payment_method", FailureCategory.EXPIRED_OR_INVALID_METHOD),
        ("mandate_failure", FailureCategory.MANDATE_OR_RECURRING_FAILURE),
        ("technical_failure", FailureCategory.TECHNICAL_FAILURE),
    ],
)
def test_payment_failure_exact_error_reason_mapping(
    error_reason: str,
    expected: FailureCategory,
) -> None:
    result = normalize_payment_failure(
        PaymentFailureEvidence(
            error_code="BAD_REQUEST_ERROR",
            error_reason=error_reason,
            error_source="gateway",
            error_step="payment_authorization",
            payment_method="UPI",
        )
    )
    assert result.failure_category == expected
    assert result.mapping_source == "error_reason"
    assert result.evidence_strength == 0.80


def test_unknown_error_reason_maps_to_unknown() -> None:
    result = normalize_payment_failure(
        PaymentFailureEvidence(
            error_code="BAD_REQUEST_ERROR",
            error_reason="totally_unmapped_provider_token",
            error_source="gateway",
            error_step="payment_authorization",
        )
    )
    assert result.failure_category == FailureCategory.UNKNOWN
    assert result.mapping_source == "unknown"
    assert result.evidence_strength == 0.40


def test_active_downtime_takes_precedence_over_generic_error_reason() -> None:
    result = normalize_payment_failure(
        PaymentFailureEvidence(
            error_code="BAD_REQUEST_ERROR",
            error_reason="insufficient_funds",
            error_source="customer",
            error_step="payment_authorization",
            payment_method="UPI",
        ),
        downtime=DowntimeContext(
            lookup_status="KNOWN",
            rail_degraded=True,
            severity="high",
            matched_method="upi",
        ),
    )
    assert result.failure_category == FailureCategory.PAYMENT_RAIL_DOWNTIME
    assert result.mapping_source == "downtime"
    assert result.evidence_strength == 1.0


def test_technical_failure_composite_mapping() -> None:
    result = normalize_payment_failure(
        PaymentFailureEvidence(
            error_code="SERVER_ERROR",
            error_reason="unmapped_reason",
            error_source="gateway",
            error_step="payment_processing",
        )
    )
    assert result.failure_category == FailureCategory.TECHNICAL_FAILURE
    assert result.mapping_source == "error_code_step_source"


def test_downtime_lookup_unknown_preserves_unknown_status() -> None:
    result = normalize_payment_failure(
        PaymentFailureEvidence(error_reason="insufficient_funds"),
        downtime=DowntimeContext(lookup_status="UNKNOWN"),
    )
    assert result.downtime_status == "UNKNOWN"


def test_subscription_pending_maps_to_mandate_or_recurring_failure() -> None:
    result = normalize_subscription_failure(
        SubscriptionFailureEvidence(provider_status="pending", retry_count=2)
    )
    assert result.failure_category == FailureCategory.MANDATE_OR_RECURRING_FAILURE
    assert result.mapping_source == "subscription_pending"


def test_subscription_halted_maps_to_mandate_or_recurring_failure() -> None:
    result = normalize_subscription_failure(
        SubscriptionFailureEvidence(provider_status="halted", retry_count=3)
    )
    assert result.failure_category == FailureCategory.MANDATE_OR_RECURRING_FAILURE
    assert result.mapping_source == "subscription_halted"


def test_subscription_metadata_reason_overrides_pending_default() -> None:
    result = normalize_subscription_failure(
        SubscriptionFailureEvidence(
            provider_status="pending",
            metadata_failure_reason="insufficient_funds",
        )
    )
    assert result.failure_category == FailureCategory.INSUFFICIENT_FUNDS
    assert result.mapping_source == "subscription_metadata_reason"


def test_error_reason_map_contains_only_documented_categories() -> None:
    assert set(ERROR_REASON_MAP.values()) <= set(FailureCategory)


_ACTIVE_DOWNTIME = DowntimeContext(
    lookup_status="KNOWN",
    rail_degraded=True,
    severity="high",
    matched_method="upi",
)


def test_subscription_pending_with_active_downtime_maps_to_downtime() -> None:
    result = normalize_subscription_failure(
        SubscriptionFailureEvidence(provider_status="pending", retry_count=2),
        downtime=_ACTIVE_DOWNTIME,
    )
    assert result.failure_category == FailureCategory.PAYMENT_RAIL_DOWNTIME
    assert result.mapping_source == "downtime"
    assert result.evidence_strength == 1.0


def test_subscription_halted_with_active_downtime_maps_to_downtime() -> None:
    result = normalize_subscription_failure(
        SubscriptionFailureEvidence(provider_status="halted", retry_count=3),
        downtime=_ACTIVE_DOWNTIME,
    )
    assert result.failure_category == FailureCategory.PAYMENT_RAIL_DOWNTIME
    assert result.mapping_source == "downtime"
    assert result.evidence_strength == 1.0


def test_subscription_metadata_reason_with_active_downtime_maps_to_downtime() -> None:
    result = normalize_subscription_failure(
        SubscriptionFailureEvidence(
            provider_status="pending",
            metadata_failure_reason="insufficient_funds",
        ),
        downtime=_ACTIVE_DOWNTIME,
    )
    assert result.failure_category == FailureCategory.PAYMENT_RAIL_DOWNTIME
    assert result.mapping_source == "downtime"
    assert result.evidence_strength == 1.0
    assert result.original_error_reason == "insufficient_funds"


def test_subscription_pending_with_unknown_downtime_lookup_stays_recurring() -> None:
    result = normalize_subscription_failure(
        SubscriptionFailureEvidence(provider_status="pending", retry_count=1),
        downtime=DowntimeContext(lookup_status="UNKNOWN"),
    )
    assert result.failure_category == FailureCategory.MANDATE_OR_RECURRING_FAILURE
    assert result.mapping_source == "subscription_pending"
    assert result.downtime_status == "UNKNOWN"


def test_subscription_pending_with_known_non_degraded_downtime_stays_recurring() -> None:
    result = normalize_subscription_failure(
        SubscriptionFailureEvidence(provider_status="pending", retry_count=1),
        downtime=DowntimeContext(lookup_status="KNOWN", rail_degraded=False),
    )
    assert result.failure_category == FailureCategory.MANDATE_OR_RECURRING_FAILURE
    assert result.mapping_source == "subscription_pending"
