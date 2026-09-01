"""Recovery engine typed schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import CaseType, FailureCategory, RecoveryActionType

FEATURE_SCHEMA_VERSION = "recovery_features_v1"

DowntimeSeverity = Literal["high", "medium", "low", "none", "unknown"]
DowntimeLookupStatus = Literal["KNOWN", "UNKNOWN", "NO_DOWNTIME"]
PaymentMethodCategory = Literal[
    "upi",
    "card",
    "netbanking",
    "wallet",
    "unknown",
]


class PaymentFailureEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    error_code: str | None = None
    error_reason: str | None = None
    error_source: str | None = None
    error_step: str | None = None
    error_description: str | None = None
    payment_method: str | None = None


class SubscriptionFailureEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider_status: str
    retry_count: int = 0
    metadata_failure_reason: str | None = None
    metadata_failure_category: str | None = None


class DowntimeContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    lookup_status: DowntimeLookupStatus = "NO_DOWNTIME"
    rail_degraded: bool = False
    severity: DowntimeSeverity = "none"
    matched_method: str | None = None


class FailureNormalizationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    failure_category: FailureCategory
    evidence_strength: float = Field(ge=0.0, le=1.0)
    mapping_source: str
    downtime_status: DowntimeLookupStatus = "NO_DOWNTIME"
    original_error_reason: str | None = None
    original_error_code: str | None = None
    original_error_source: str | None = None
    original_error_step: str | None = None
    provider_status: str | None = None


class TransactionSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    organization_id: UUID
    customer_id: UUID
    amount_minor: int = Field(ge=0)
    currency: str
    status: str
    payment_method: str | None = None
    error_code: str | None = None
    error_reason: str | None = None
    error_source: str | None = None
    error_step: str | None = None
    provider_created_at: datetime | None = None


class SubscriptionSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    id: UUID
    organization_id: UUID
    customer_id: UUID
    amount_minor: int = Field(ge=0)
    currency: str
    status: str
    retry_count: int = 0
    metadata_: dict = Field(default_factory=dict, alias="metadata")


class CustomerSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    organization_id: UUID
    segment: str
    lifetime_value_minor: int = Field(ge=0)
    created_at: datetime


class CaseSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    organization_id: UUID
    customer_id: UUID
    case_type: CaseType
    amount_at_risk_minor: int = Field(ge=0)
    currency: str
    opened_at: datetime
    failure_category: str | None = None


class RecoveryFeaturesV1(BaseModel):
    """Immutable recovery_features_v1 case-level feature vector."""

    model_config = ConfigDict(frozen=True)

    feature_schema_version: str = FEATURE_SCHEMA_VERSION

    amount_minor: int = Field(ge=0)
    amount_log1p: float
    hours_since_failure: float
    hour_of_day: int = Field(ge=0, le=23)
    day_of_week: int = Field(ge=0, le=6)

    customer_tenure_days: float | None = None
    customer_tenure_days_missing: bool = False
    successful_payments_90d: int | None = None
    successful_payments_90d_missing: bool = False
    failed_payments_30d: int | None = None
    failed_payments_30d_missing: bool = False
    payment_success_rate_90d: float | None = None
    payment_success_rate_90d_missing: bool = False
    historical_recovery_rate: float | None = None
    historical_recovery_rate_missing: bool = True
    lifetime_value_minor: int = Field(ge=0)
    lifetime_value_log1p: float

    retry_count_provider: int | None = None
    retry_count_provider_missing: bool = False
    recovery_attempts_so_far: int = Field(ge=0)
    contacts_last_24h: int = Field(ge=0)

    rail_degraded: bool
    same_method_recent_success: bool
    alternate_method_recent_success: bool
    is_subscription: bool

    case_type: str
    failure_category: str
    payment_method: str
    customer_segment: str
    downtime_severity: DowntimeSeverity

    action_type: str | None = None

    feature_completeness: float = Field(ge=0.0, le=1.0)
    evidence_strength: float = Field(ge=0.0, le=1.0)

    @field_validator("payment_success_rate_90d", "historical_recovery_rate")
    @classmethod
    def validate_rate_range(cls, value: float | None) -> float | None:
        if value is None:
            return value
        if not 0.0 <= value <= 1.0:
            raise ValueError("Rate features must be within [0, 1].")
        return value


class FeatureBuildInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    case: CaseSnapshot
    customer: CustomerSnapshot
    normalization: FailureNormalizationResult
    current_time: datetime
    transaction: TransactionSnapshot | None = None
    subscription: SubscriptionSnapshot | None = None
    prior_transactions: tuple[TransactionSnapshot, ...] = ()
    downtime: DowntimeContext | None = None
    recovery_attempts_so_far: int = Field(default=0, ge=0)
    contacts_last_24h: int = Field(default=0, ge=0)
    prior_recovery_cases_total: int | None = Field(default=None, ge=0)
    prior_recovery_cases_recovered: int | None = Field(default=None, ge=0)
    action_type: RecoveryActionType | None = None

    @field_validator("prior_recovery_cases_recovered")
    @classmethod
    def validate_recovered_not_exceed_total(
        cls,
        recovered: int | None,
        info,
    ) -> int | None:
        total = info.data.get("prior_recovery_cases_total")
        if recovered is not None and total is not None and recovered > total:
            raise ValueError("prior_recovery_cases_recovered cannot exceed total.")
        return recovered
