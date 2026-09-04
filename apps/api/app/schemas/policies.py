"""Read-only merchant policy schema.

Surfaces the same MerchantPolicy row the policy engine actually enforces
(app/policies/engine.py) -- this is not a marketing description of safety
behavior, it is the literal enforced configuration, read back.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.enums import RecoveryActionType


class PolicyResponse(BaseModel):
    currency: str
    auto_action_limit_minor: int
    max_recovery_attempts: int
    max_contacts_per_24h: int
    minimum_auto_confidence: float = Field(ge=0.0, le=1.0)
    cooldown_minutes: int
    automation_enabled: bool
    allowed_action_types: list[RecoveryActionType]
    manual_contact_approval_action_types: list[RecoveryActionType]
    contact_action_types: list[RecoveryActionType]
    cooldown_action_types: list[RecoveryActionType]
