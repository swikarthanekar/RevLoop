"""Read-only merchant policy route.

Surfaces the literal MerchantPolicy configuration the policy engine enforces
on every recovery decision -- the "Compliance Guardrails" the case detail
screen's policy_reasons already reference case by case, made visible as one
standing view instead of only ever appearing after the fact.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import AuthContext, get_current_user
from app.core.deps import get_db
from app.core.errors import NotFoundError
from app.domain.enums import RecoveryActionType
from app.models.merchant_policy import MerchantPolicy
from app.policies.engine import (
    _contact_action_types,
    _cooldown_action_types,
    _manual_contact_actions,
)
from app.policies.schemas import MerchantPolicyConfig
from app.recovery.service import merchant_policy_from_model
from app.schemas.policies import PolicyResponse

router = APIRouter(prefix="/policies", tags=["policies"])


def _to_response(policy: MerchantPolicy) -> PolicyResponse:
    config: MerchantPolicyConfig = merchant_policy_from_model(policy)
    allowed = sorted(config.allowed_action_types, key=lambda action: action.value)
    return PolicyResponse(
        currency=policy.organization.currency,
        auto_action_limit_minor=config.auto_action_limit_minor,
        max_recovery_attempts=config.max_recovery_attempts,
        max_contacts_per_24h=config.max_contacts_per_24h,
        minimum_auto_confidence=float(config.minimum_auto_confidence),
        cooldown_minutes=config.cooldown_minutes,
        automation_enabled=config.automation_enabled,
        allowed_action_types=list(allowed),
        manual_contact_approval_action_types=_sorted(_manual_contact_actions(config)),
        contact_action_types=_sorted(_contact_action_types(config)),
        cooldown_action_types=_sorted(_cooldown_action_types(config)),
    )


def _sorted(actions: frozenset[RecoveryActionType]) -> list[RecoveryActionType]:
    return sorted(actions, key=lambda action: action.value)


@router.get("", response_model=PolicyResponse)
def get_policy(
    current_user: Annotated[AuthContext, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> PolicyResponse:
    policy = db.execute(
        select(MerchantPolicy).where(
            MerchantPolicy.organization_id == current_user.organization_id
        )
    ).scalar_one_or_none()
    if policy is None:
        raise NotFoundError(code="POLICY_NOT_FOUND", message="No policy configured.")
    return _to_response(policy)
