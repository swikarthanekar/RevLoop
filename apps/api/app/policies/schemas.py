"""Policy engine typed contracts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import RecoveryActionType
from app.policies.reason_codes import PolicyReasonCode


class MerchantPolicyConfig(BaseModel):
    """Runtime merchant policy inputs; mirrors persisted P0 fields."""

    model_config = ConfigDict(frozen=True)

    auto_action_limit_minor: int = Field(ge=0)
    max_recovery_attempts: int = Field(ge=0)
    max_contacts_per_24h: int = Field(ge=0)
    minimum_auto_confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    cooldown_minutes: int = Field(ge=0)
    automation_enabled: bool
    allowed_action_types: frozenset[RecoveryActionType]
    approval_only_action_types: frozenset[RecoveryActionType] = Field(default_factory=frozenset)
    contact_action_types: frozenset[RecoveryActionType] = Field(default_factory=frozenset)
    cooldown_action_types: frozenset[RecoveryActionType] = Field(default_factory=frozenset)
    manual_contact_approval_action_types: frozenset[RecoveryActionType] = Field(
        default_factory=frozenset
    )


class PolicyEvaluationContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    action_type: RecoveryActionType
    amount_at_risk_minor: int = Field(ge=0)
    recovery_attempts_so_far: int = Field(ge=0)
    contacts_last_24h: int = Field(ge=0)
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    expected_value_minor: int
    payment_link_data_sufficient: bool = False
    case_terminal: bool = False
    provider_success_known: bool = False
    verified_rail_downtime: bool = False
    equivalent_actions_in_flight: frozenset[RecoveryActionType] = Field(default_factory=frozenset)
    auto_execution_requested: bool = False
    cooldown_elapsed_minutes: int | None = None
    last_retry_or_contact_at: datetime | None = None
    provider_retries_active: bool = False


class PolicyDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    eligible: bool
    requires_approval: bool
    reasons: tuple[PolicyReasonCode, ...] = ()

    @field_validator("reasons")
    @classmethod
    def validate_unique_reasons(
        cls,
        reasons: tuple[PolicyReasonCode, ...],
    ) -> tuple[PolicyReasonCode, ...]:
        if len(reasons) != len(set(reasons)):
            raise ValueError("Policy reasons must not contain duplicates.")
        return reasons
