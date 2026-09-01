"""Deterministic failure normalization from provider evidence."""

from __future__ import annotations

from app.domain.enums import FailureCategory
from app.recovery.schemas import (
    DowntimeContext,
    FailureNormalizationResult,
    PaymentFailureEvidence,
    SubscriptionFailureEvidence,
)

# Verified fixture/doc mappings only — exact token matches, no substring rules.
ERROR_REASON_MAP: dict[str, FailureCategory] = {
    "payment_rail_unavailable": FailureCategory.PAYMENT_RAIL_DOWNTIME,
    "insufficient_funds": FailureCategory.INSUFFICIENT_FUNDS,
    "payment_authentication_failure": FailureCategory.AUTHENTICATION_FAILURE,
    "bank_declined": FailureCategory.BANK_OR_ISSUER_DECLINE,
    "expired_payment_method": FailureCategory.EXPIRED_OR_INVALID_METHOD,
    "mandate_failure": FailureCategory.MANDATE_OR_RECURRING_FAILURE,
    "technical_failure": FailureCategory.TECHNICAL_FAILURE,
}

# Verified composite mapping for technical processing failures.
ERROR_CODE_STEP_SOURCE_MAP: dict[tuple[str, str, str], FailureCategory] = {
    ("SERVER_ERROR", "payment_processing", "gateway"): FailureCategory.TECHNICAL_FAILURE,
}

SUBSCRIPTION_PENDING_STATUS = "pending"
SUBSCRIPTION_HALTED_STATUS = "halted"


def _partial_evidence_strength(
    *,
    has_error_reason: bool,
    has_error_code: bool,
    has_error_step: bool,
    has_error_source: bool,
    has_downtime_context: bool,
    is_subscription: bool,
) -> float:
    if has_downtime_context and (has_error_reason or is_subscription):
        return 1.0
    if has_error_reason:
        return 0.80
    if has_error_code and (has_error_step or has_error_source):
        return 0.65
    return 0.40


def normalize_payment_failure(
    evidence: PaymentFailureEvidence,
    *,
    downtime: DowntimeContext | None = None,
) -> FailureNormalizationResult:
    downtime_ctx = downtime or DowntimeContext()
    has_reason = evidence.error_reason is not None
    has_code = evidence.error_code is not None
    has_step = evidence.error_step is not None
    has_source = evidence.error_source is not None

    if downtime_ctx.lookup_status == "KNOWN" and downtime_ctx.rail_degraded:
        strength = _partial_evidence_strength(
            has_error_reason=has_reason,
            has_error_code=has_code,
            has_error_step=has_step,
            has_error_source=has_source,
            has_downtime_context=True,
            is_subscription=False,
        )
        return FailureNormalizationResult(
            failure_category=FailureCategory.PAYMENT_RAIL_DOWNTIME,
            evidence_strength=strength,
            mapping_source="downtime",
            downtime_status=downtime_ctx.lookup_status,
            original_error_reason=evidence.error_reason,
            original_error_code=evidence.error_code,
            original_error_source=evidence.error_source,
            original_error_step=evidence.error_step,
        )

    if evidence.error_reason is not None:
        mapped = ERROR_REASON_MAP.get(evidence.error_reason)
        if mapped is not None:
            strength = _partial_evidence_strength(
                has_error_reason=True,
                has_error_code=has_code,
                has_error_step=has_step,
                has_error_source=has_source,
                has_downtime_context=False,
                is_subscription=False,
            )
            return FailureNormalizationResult(
                failure_category=mapped,
                evidence_strength=strength,
                mapping_source="error_reason",
                downtime_status=downtime_ctx.lookup_status,
                original_error_reason=evidence.error_reason,
                original_error_code=evidence.error_code,
                original_error_source=evidence.error_source,
                original_error_step=evidence.error_step,
            )

    if (
        evidence.error_code is not None
        and evidence.error_step is not None
        and evidence.error_source is not None
    ):
        composite_key = (
            evidence.error_code,
            evidence.error_step,
            evidence.error_source,
        )
        mapped = ERROR_CODE_STEP_SOURCE_MAP.get(composite_key)
        if mapped is not None:
            return FailureNormalizationResult(
                failure_category=mapped,
                evidence_strength=0.65,
                mapping_source="error_code_step_source",
                downtime_status=downtime_ctx.lookup_status,
                original_error_reason=evidence.error_reason,
                original_error_code=evidence.error_code,
                original_error_source=evidence.error_source,
                original_error_step=evidence.error_step,
            )

    return FailureNormalizationResult(
        failure_category=FailureCategory.UNKNOWN,
        evidence_strength=0.40,
        mapping_source="unknown",
        downtime_status=downtime_ctx.lookup_status,
        original_error_reason=evidence.error_reason,
        original_error_code=evidence.error_code,
        original_error_source=evidence.error_source,
        original_error_step=evidence.error_step,
    )


def normalize_subscription_failure(
    evidence: SubscriptionFailureEvidence,
    *,
    downtime: DowntimeContext | None = None,
) -> FailureNormalizationResult:
    downtime_ctx = downtime or DowntimeContext()
    status = evidence.provider_status.lower()
    has_metadata_reason = evidence.metadata_failure_reason is not None

    if downtime_ctx.lookup_status == "KNOWN" and downtime_ctx.rail_degraded:
        strength = _partial_evidence_strength(
            has_error_reason=has_metadata_reason,
            has_error_code=False,
            has_error_step=False,
            has_error_source=False,
            has_downtime_context=True,
            is_subscription=True,
        )
        return FailureNormalizationResult(
            failure_category=FailureCategory.PAYMENT_RAIL_DOWNTIME,
            evidence_strength=strength,
            mapping_source="downtime",
            downtime_status=downtime_ctx.lookup_status,
            original_error_reason=evidence.metadata_failure_reason,
            provider_status=evidence.provider_status,
        )

    if evidence.metadata_failure_reason is not None:
        mapped = ERROR_REASON_MAP.get(evidence.metadata_failure_reason)
        if mapped is not None:
            strength = _partial_evidence_strength(
                has_error_reason=True,
                has_error_code=False,
                has_error_step=False,
                has_error_source=False,
                has_downtime_context=downtime_ctx.rail_degraded,
                is_subscription=True,
            )
            return FailureNormalizationResult(
                failure_category=mapped,
                evidence_strength=strength,
                mapping_source="subscription_metadata_reason",
                downtime_status=downtime_ctx.lookup_status,
                original_error_reason=evidence.metadata_failure_reason,
                provider_status=evidence.provider_status,
            )

    if status == SUBSCRIPTION_PENDING_STATUS:
        strength = _partial_evidence_strength(
            has_error_reason=False,
            has_error_code=False,
            has_error_step=False,
            has_error_source=False,
            has_downtime_context=downtime_ctx.rail_degraded,
            is_subscription=True,
        )
        return FailureNormalizationResult(
            failure_category=FailureCategory.MANDATE_OR_RECURRING_FAILURE,
            evidence_strength=strength,
            mapping_source="subscription_pending",
            downtime_status=downtime_ctx.lookup_status,
            provider_status=evidence.provider_status,
        )

    if status == SUBSCRIPTION_HALTED_STATUS:
        strength = _partial_evidence_strength(
            has_error_reason=False,
            has_error_code=False,
            has_error_step=False,
            has_error_source=False,
            has_downtime_context=downtime_ctx.rail_degraded,
            is_subscription=True,
        )
        return FailureNormalizationResult(
            failure_category=FailureCategory.MANDATE_OR_RECURRING_FAILURE,
            evidence_strength=strength,
            mapping_source="subscription_halted",
            downtime_status=downtime_ctx.lookup_status,
            provider_status=evidence.provider_status,
        )

    return FailureNormalizationResult(
        failure_category=FailureCategory.UNKNOWN,
        evidence_strength=0.40,
        mapping_source="unknown",
        downtime_status=downtime_ctx.lookup_status,
        provider_status=evidence.provider_status,
    )
