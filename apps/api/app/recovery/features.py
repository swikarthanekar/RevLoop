"""Deterministic recovery_features_v1 construction."""

from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone

from app.domain.enums import CaseType
from app.recovery.schemas import (
    FEATURE_SCHEMA_VERSION,
    DowntimeContext,
    DowntimeSeverity,
    FeatureBuildInput,
    RecoveryFeaturesV1,
    TransactionSnapshot,
)

IMPORTANT_FEATURE_KEYS: tuple[str, ...] = (
    "amount_minor",
    "amount_log1p",
    "hours_since_failure",
    "hour_of_day",
    "day_of_week",
    "customer_tenure_days",
    "successful_payments_90d",
    "failed_payments_30d",
    "payment_success_rate_90d",
    "historical_recovery_rate",
    "lifetime_value_minor",
    "lifetime_value_log1p",
    "retry_count_provider",
    "recovery_attempts_so_far",
    "contacts_last_24h",
    "rail_degraded",
    "same_method_recent_success",
    "alternate_method_recent_success",
    "is_subscription",
    "case_type",
    "failure_category",
    "payment_method",
    "customer_segment",
    "downtime_severity",
)

SUCCESS_STATUSES = frozenset({"captured", "paid", "success"})
FAILED_STATUSES = frozenset({"failed"})


def _normalize_payment_method(method: str | None) -> str:
    if method is None or not method.strip():
        return "unknown"
    return method.strip().lower()


def _failure_timestamp(input_data: FeatureBuildInput) -> datetime:
    txn = input_data.transaction
    if txn is not None and txn.provider_created_at is not None:
        return txn.provider_created_at
    return input_data.case.opened_at


def _eligible_transactions(
    transactions: Iterable[TransactionSnapshot],
    *,
    failure_at: datetime,
) -> list[TransactionSnapshot]:
    eligible: list[TransactionSnapshot] = []
    for txn in transactions:
        if txn.provider_created_at is None:
            continue
        if txn.provider_created_at >= failure_at:
            continue
        eligible.append(txn)
    return eligible


def compute_payment_history_features(
    transactions: Iterable[TransactionSnapshot],
    *,
    failure_at: datetime,
    current_time: datetime,
    payment_method: str | None,
) -> dict[str, object]:
    eligible = _eligible_transactions(transactions, failure_at=failure_at)
    normalized_method = _normalize_payment_method(payment_method)

    window_90d_start = failure_at - timedelta(days=90)
    window_30d_start = failure_at - timedelta(days=30)

    attempts_90d = [
        txn
        for txn in eligible
        if txn.provider_created_at is not None and txn.provider_created_at >= window_90d_start
    ]
    failed_30d = [
        txn
        for txn in eligible
        if txn.provider_created_at is not None
        and txn.provider_created_at >= window_30d_start
        and txn.status.lower() in FAILED_STATUSES
    ]
    successes_90d = [
        txn
        for txn in attempts_90d
        if txn.status.lower() in SUCCESS_STATUSES
    ]

    if not eligible:
        return {
            "successful_payments_90d": None,
            "successful_payments_90d_missing": True,
            "failed_payments_30d": None,
            "failed_payments_30d_missing": True,
            "payment_success_rate_90d": None,
            "payment_success_rate_90d_missing": True,
            "same_method_recent_success": False,
            "alternate_method_recent_success": False,
        }

    success_count = len(successes_90d)
    attempt_count = len(attempts_90d)
    success_rate: float | None
    success_rate_missing: bool
    if attempt_count == 0:
        success_rate = None
        success_rate_missing = True
    else:
        success_rate = success_count / attempt_count
        success_rate_missing = False

    same_method_success = any(
        txn.status.lower() in SUCCESS_STATUSES
        and _normalize_payment_method(txn.payment_method) == normalized_method
        and normalized_method != "unknown"
        for txn in attempts_90d
    )
    alternate_method_success = any(
        txn.status.lower() in SUCCESS_STATUSES
        and _normalize_payment_method(txn.payment_method) not in {normalized_method, "unknown"}
        for txn in successes_90d
    )

    return {
        "successful_payments_90d": success_count,
        "successful_payments_90d_missing": False,
        "failed_payments_30d": len(failed_30d),
        "failed_payments_30d_missing": False,
        "payment_success_rate_90d": success_rate,
        "payment_success_rate_90d_missing": success_rate_missing,
        "same_method_recent_success": same_method_success,
        "alternate_method_recent_success": alternate_method_success,
    }


def compute_historical_recovery_rate(
    *,
    prior_total: int | None,
    prior_recovered: int | None,
) -> tuple[float | None, bool]:
    if prior_total is None or prior_recovered is None:
        return None, True
    if prior_total == 0:
        return None, True
    return prior_recovered / prior_total, False


def compute_feature_completeness(features: RecoveryFeaturesV1) -> float:
    present = 0
    for key in IMPORTANT_FEATURE_KEYS:
        value = getattr(features, key)
        missing_flag = getattr(features, f"{key}_missing", None)
        if missing_flag is True:
            continue
        if isinstance(value, str) and value == "unknown":
            continue
        if value is None:
            continue
        present += 1
    return present / len(IMPORTANT_FEATURE_KEYS)


def _downtime_severity(downtime: DowntimeContext | None) -> DowntimeSeverity:
    if downtime is None:
        return "none"
    if downtime.lookup_status == "UNKNOWN":
        return "unknown"
    if not downtime.rail_degraded:
        return "none"
    return downtime.severity


def build_recovery_features_v1(input_data: FeatureBuildInput) -> RecoveryFeaturesV1:
    failure_at = _failure_timestamp(input_data)
    current_time = input_data.current_time
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    if failure_at.tzinfo is None:
        failure_at = failure_at.replace(tzinfo=timezone.utc)

    hours_since_failure = max(
        0.0,
        (current_time - failure_at).total_seconds() / 3600.0,
    )

    payment_method = None
    retry_count_provider: int | None = None
    retry_missing = True
    is_subscription = input_data.case.case_type == CaseType.SUBSCRIPTION_FAILURE

    if input_data.transaction is not None:
        payment_method = input_data.transaction.payment_method
        retry_missing = True
    elif input_data.subscription is not None:
        payment_method = "unknown"
        retry_count_provider = input_data.subscription.retry_count
        retry_missing = False

    history = compute_payment_history_features(
        input_data.prior_transactions,
        failure_at=failure_at,
        current_time=current_time,
        payment_method=payment_method,
    )

    customer_created = input_data.customer.created_at
    if customer_created.tzinfo is None:
        customer_created = customer_created.replace(tzinfo=timezone.utc)
    tenure_days = max(0.0, (failure_at - customer_created).total_seconds() / 86400.0)
    tenure_missing = False

    hist_rate, hist_missing = compute_historical_recovery_rate(
        prior_total=input_data.prior_recovery_cases_total,
        prior_recovered=input_data.prior_recovery_cases_recovered,
    )

    downtime = input_data.downtime or DowntimeContext()
    failure_category = input_data.normalization.failure_category.value
    lifetime_value_minor = input_data.customer.lifetime_value_minor

    features = RecoveryFeaturesV1(
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        amount_minor=input_data.case.amount_at_risk_minor,
        amount_log1p=math.log1p(input_data.case.amount_at_risk_minor),
        hours_since_failure=hours_since_failure,
        hour_of_day=failure_at.hour,
        day_of_week=failure_at.weekday(),
        customer_tenure_days=tenure_days,
        customer_tenure_days_missing=tenure_missing,
        successful_payments_90d=history["successful_payments_90d"],  # type: ignore[arg-type]
        successful_payments_90d_missing=history["successful_payments_90d_missing"],  # type: ignore[arg-type]
        failed_payments_30d=history["failed_payments_30d"],  # type: ignore[arg-type]
        failed_payments_30d_missing=history["failed_payments_30d_missing"],  # type: ignore[arg-type]
        payment_success_rate_90d=history["payment_success_rate_90d"],  # type: ignore[arg-type]
        payment_success_rate_90d_missing=history["payment_success_rate_90d_missing"],  # type: ignore[arg-type]
        historical_recovery_rate=hist_rate,
        historical_recovery_rate_missing=hist_missing,
        lifetime_value_minor=lifetime_value_minor,
        lifetime_value_log1p=math.log1p(lifetime_value_minor),
        retry_count_provider=retry_count_provider,
        retry_count_provider_missing=retry_missing,
        recovery_attempts_so_far=input_data.recovery_attempts_so_far,
        contacts_last_24h=input_data.contacts_last_24h,
        rail_degraded=downtime.rail_degraded,
        same_method_recent_success=history["same_method_recent_success"],  # type: ignore[arg-type]
        alternate_method_recent_success=history["alternate_method_recent_success"],  # type: ignore[arg-type]
        is_subscription=is_subscription,
        case_type=input_data.case.case_type.value,
        failure_category=failure_category,
        payment_method=_normalize_payment_method(payment_method),
        customer_segment=input_data.customer.segment,
        downtime_severity=_downtime_severity(downtime),
        action_type=input_data.action_type.value if input_data.action_type else None,
        feature_completeness=0.0,
        evidence_strength=input_data.normalization.evidence_strength,
    )

    completeness = compute_feature_completeness(features)
    return features.model_copy(update={"feature_completeness": completeness})
