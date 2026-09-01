"""RecoveryFeaturesV1 builder tests."""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.domain.enums import CaseType, FailureCategory
from app.recovery.features import (
    build_recovery_features_v1,
    compute_feature_completeness,
    compute_payment_history_features,
)
from app.recovery.schemas import (
    FEATURE_SCHEMA_VERSION,
    CaseSnapshot,
    CustomerSnapshot,
    FailureNormalizationResult,
    FeatureBuildInput,
    RecoveryFeaturesV1,
    SubscriptionSnapshot,
    TransactionSnapshot,
)

UTC = datetime(2026, 8, 30, 12, 0, 0, tzinfo=timezone.utc)


def _case() -> CaseSnapshot:
    return CaseSnapshot(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        customer_id=uuid.uuid4(),
        case_type=CaseType.PAYMENT_FAILURE,
        amount_at_risk_minor=499900,
        currency="INR",
        opened_at=UTC,
    )


def _customer(customer_id: uuid.UUID, org_id: uuid.UUID) -> CustomerSnapshot:
    return CustomerSnapshot(
        id=customer_id,
        organization_id=org_id,
        segment="REGULAR",
        lifetime_value_minor=1_000_000,
        created_at=UTC - timedelta(days=120),
    )


def _normalization(category: FailureCategory = FailureCategory.INSUFFICIENT_FUNDS):
    return FailureNormalizationResult(
        failure_category=category,
        evidence_strength=0.80,
        mapping_source="error_reason",
    )


def _txn(
    *,
    customer_id: uuid.UUID,
    org_id: uuid.UUID,
    created_at: datetime,
    status: str = "captured",
    method: str = "UPI",
    amount: int = 99900,
) -> TransactionSnapshot:
    return TransactionSnapshot(
        id=uuid.uuid4(),
        organization_id=org_id,
        customer_id=customer_id,
        amount_minor=amount,
        currency="INR",
        status=status,
        payment_method=method,
        provider_created_at=created_at,
    )


def test_build_features_v1_has_expected_schema_version() -> None:
    case = _case()
    customer = _customer(case.customer_id, case.organization_id)
    failure_txn = _txn(
        customer_id=case.customer_id,
        org_id=case.organization_id,
        created_at=UTC - timedelta(hours=2),
        status="failed",
        method="UPI",
    )

    features = build_recovery_features_v1(
        FeatureBuildInput(
            case=case,
            customer=customer,
            normalization=_normalization(),
            current_time=UTC,
            transaction=failure_txn,
        )
    )

    assert features.feature_schema_version == FEATURE_SCHEMA_VERSION
    assert features.amount_minor == 499900
    assert features.case_type == CaseType.PAYMENT_FAILURE.value
    assert features.failure_category == FailureCategory.INSUFFICIENT_FUNDS.value
    assert features.payment_method == "upi"
    assert features.evidence_strength == 0.80
    assert 0.0 <= features.feature_completeness <= 1.0


def test_lookback_excludes_future_and_failure_timestamp_transactions() -> None:
    org_id = uuid.uuid4()
    customer_id = uuid.uuid4()
    failure_at = UTC

    prior_success = _txn(
        customer_id=customer_id,
        org_id=org_id,
        created_at=failure_at - timedelta(days=10),
        status="captured",
        method="UPI",
    )
    same_moment = _txn(
        customer_id=customer_id,
        org_id=org_id,
        created_at=failure_at,
        status="captured",
        method="CARD",
    )
    future = _txn(
        customer_id=customer_id,
        org_id=org_id,
        created_at=failure_at + timedelta(hours=1),
        status="captured",
        method="CARD",
    )

    history = compute_payment_history_features(
        (prior_success, same_moment, future),
        failure_at=failure_at,
        current_time=UTC,
        payment_method="UPI",
    )

    assert history["successful_payments_90d"] == 1
    assert history["same_method_recent_success"] is True
    assert history["alternate_method_recent_success"] is False


def test_missing_history_marks_missing_flags() -> None:
    case = _case()
    customer = _customer(case.customer_id, case.organization_id)
    failure_txn = _txn(
        customer_id=case.customer_id,
        org_id=case.organization_id,
        created_at=UTC - timedelta(hours=1),
        status="failed",
    )

    features = build_recovery_features_v1(
        FeatureBuildInput(
            case=case,
            customer=customer,
            normalization=_normalization(),
            current_time=UTC,
            transaction=failure_txn,
            prior_transactions=(),
        )
    )

    assert features.successful_payments_90d_missing is True
    assert features.failed_payments_30d_missing is True
    assert features.payment_success_rate_90d_missing is True
    assert features.historical_recovery_rate_missing is True


def test_historical_recovery_rate_uses_prior_cases_only() -> None:
    case = _case()
    customer = _customer(case.customer_id, case.organization_id)
    features = build_recovery_features_v1(
        FeatureBuildInput(
            case=case,
            customer=customer,
            normalization=_normalization(),
            current_time=UTC,
            prior_recovery_cases_total=4,
            prior_recovery_cases_recovered=1,
        )
    )
    assert features.historical_recovery_rate == 0.25
    assert features.historical_recovery_rate_missing is False


def test_subscription_case_sets_is_subscription_and_retry_count() -> None:
    case = CaseSnapshot(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        customer_id=uuid.uuid4(),
        case_type=CaseType.SUBSCRIPTION_FAILURE,
        amount_at_risk_minor=149900,
        currency="INR",
        opened_at=UTC,
    )
    customer = _customer(case.customer_id, case.organization_id)

    features = build_recovery_features_v1(
        FeatureBuildInput(
            case=case,
            customer=customer,
            normalization=_normalization(FailureCategory.MANDATE_OR_RECURRING_FAILURE),
            current_time=UTC,
            subscription=SubscriptionSnapshot(
                id=uuid.uuid4(),
                organization_id=case.organization_id,
                customer_id=case.customer_id,
                amount_minor=149900,
                currency="INR",
                status="pending",
                retry_count=2,
            ),
        )
    )

    assert features.is_subscription is True
    assert features.retry_count_provider == 2
    assert features.retry_count_provider_missing is False


def test_feature_completeness_decreases_with_missing_history() -> None:
    case = _case()
    customer = _customer(case.customer_id, case.organization_id)

    rich = build_recovery_features_v1(
        FeatureBuildInput(
            case=case,
            customer=customer,
            normalization=_normalization(),
            current_time=UTC,
            transaction=_txn(
                customer_id=case.customer_id,
                org_id=case.organization_id,
                created_at=UTC - timedelta(hours=3),
                status="failed",
                method="UPI",
            ),
            prior_transactions=(
                _txn(
                    customer_id=case.customer_id,
                    org_id=case.organization_id,
                    created_at=UTC - timedelta(days=5),
                    status="captured",
                    method="UPI",
                ),
            ),
            prior_recovery_cases_total=2,
            prior_recovery_cases_recovered=1,
        )
    )
    sparse = build_recovery_features_v1(
        FeatureBuildInput(
            case=case,
            customer=customer,
            normalization=_normalization(FailureCategory.UNKNOWN),
            current_time=UTC,
        )
    )

    assert rich.feature_completeness > sparse.feature_completeness


def test_features_do_not_accept_outcome_fields() -> None:
    fields = set(RecoveryFeaturesV1.model_fields)
    forbidden = {
        "recovered_amount_minor",
        "outcome",
        "recovery_status",
        "action_status",
        "action_result",
    }
    assert forbidden.isdisjoint(fields)


def test_no_post_outcome_leakage_in_history_counts() -> None:
    org_id = uuid.uuid4()
    customer_id = uuid.uuid4()
    failure_at = UTC - timedelta(days=1)

    pre_success = _txn(
        customer_id=customer_id,
        org_id=org_id,
        created_at=failure_at - timedelta(days=2),
        status="captured",
    )
    post_success = _txn(
        customer_id=customer_id,
        org_id=org_id,
        created_at=failure_at + timedelta(hours=6),
        status="captured",
    )

    history = compute_payment_history_features(
        (pre_success, post_success),
        failure_at=failure_at,
        current_time=UTC,
        payment_method="UPI",
    )

    assert history["successful_payments_90d"] == 1


def test_compute_feature_completeness_is_deterministic() -> None:
    case = _case()
    customer = _customer(case.customer_id, case.organization_id)
    features = build_recovery_features_v1(
        FeatureBuildInput(
            case=case,
            customer=customer,
            normalization=_normalization(),
            current_time=UTC,
        )
    )
    assert compute_feature_completeness(features) == pytest.approx(features.feature_completeness)


def test_lifetime_value_minor_preserved_exactly() -> None:
    case = _case()
    customer = CustomerSnapshot(
        id=case.customer_id,
        organization_id=case.organization_id,
        segment="REGULAR",
        lifetime_value_minor=2_500_000,
        created_at=UTC - timedelta(days=60),
    )
    features = build_recovery_features_v1(
        FeatureBuildInput(
            case=case,
            customer=customer,
            normalization=_normalization(),
            current_time=UTC,
        )
    )
    assert features.lifetime_value_minor == 2_500_000


def test_lifetime_value_log1p_derived_from_minor_units() -> None:
    case = _case()
    ltv_minor = 1_000_000
    customer = CustomerSnapshot(
        id=case.customer_id,
        organization_id=case.organization_id,
        segment="REGULAR",
        lifetime_value_minor=ltv_minor,
        created_at=UTC - timedelta(days=60),
    )
    features = build_recovery_features_v1(
        FeatureBuildInput(
            case=case,
            customer=customer,
            normalization=_normalization(),
            current_time=UTC,
        )
    )
    assert features.lifetime_value_log1p == pytest.approx(math.log1p(ltv_minor))


def test_zero_lifetime_value_minor_and_log1p() -> None:
    case = _case()
    customer = CustomerSnapshot(
        id=case.customer_id,
        organization_id=case.organization_id,
        segment="REGULAR",
        lifetime_value_minor=0,
        created_at=UTC - timedelta(days=30),
    )
    features = build_recovery_features_v1(
        FeatureBuildInput(
            case=case,
            customer=customer,
            normalization=_normalization(),
            current_time=UTC,
        )
    )
    assert features.lifetime_value_minor == 0
    assert features.lifetime_value_log1p == pytest.approx(0.0)


def test_negative_lifetime_value_rejected_at_snapshot_boundary() -> None:
    case = _case()
    with pytest.raises(ValidationError):
        CustomerSnapshot(
            id=case.customer_id,
            organization_id=case.organization_id,
            segment="REGULAR",
            lifetime_value_minor=-100,
            created_at=UTC - timedelta(days=30),
        )
