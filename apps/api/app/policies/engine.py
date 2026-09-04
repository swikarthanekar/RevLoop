"""Deterministic merchant policy evaluation."""

from __future__ import annotations

from app.domain.enums import PAYMENT_LINK_MECHANISM_ACTIONS, RecoveryActionType
from app.policies.reason_codes import (
    HARD_BLOCK_REASON_CODES,
    PolicyReasonCode,
    sort_policy_reasons,
)
from app.policies.schemas import MerchantPolicyConfig, PolicyDecision, PolicyEvaluationContext
from app.recovery.erv import CONTACT_ACTION_TYPES

# P0 configuration: actions subject to retry/customer-contact cooldown.
DEFAULT_COOLDOWN_ACTION_TYPES: frozenset[RecoveryActionType] = frozenset(
    {
        RecoveryActionType.RETRY_SAME_METHOD,
        RecoveryActionType.SEND_RECOVERY_MESSAGE,
    }
)

# P0 configuration: RevLoop business recovery interventions for attempt-cap policy.
RECOVERY_INTERVENTION_ACTION_TYPES: frozenset[RecoveryActionType] = frozenset(
    {
        RecoveryActionType.WAIT,
        RecoveryActionType.RETRY_SAME_METHOD,
        RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD,
        RecoveryActionType.CREATE_PAYMENT_LINK,
        RecoveryActionType.SEND_RECOVERY_MESSAGE,
        RecoveryActionType.ESCALATE_TO_HUMAN,
    }
)

DEFAULT_CONTACT_ACTION_TYPES = CONTACT_ACTION_TYPES
DEFAULT_MANUAL_CONTACT_APPROVAL_ACTION_TYPES: frozenset[RecoveryActionType] = frozenset(
    {RecoveryActionType.ESCALATE_TO_HUMAN}
)


def _is_cooldown_active(context: PolicyEvaluationContext, policy: MerchantPolicyConfig) -> bool:
    if context.cooldown_elapsed_minutes is None:
        return False
    return context.cooldown_elapsed_minutes < policy.cooldown_minutes


def _contact_action_types(policy: MerchantPolicyConfig) -> frozenset[RecoveryActionType]:
    if policy.contact_action_types:
        return policy.contact_action_types
    return DEFAULT_CONTACT_ACTION_TYPES


def _cooldown_action_types(policy: MerchantPolicyConfig) -> frozenset[RecoveryActionType]:
    if policy.cooldown_action_types:
        return policy.cooldown_action_types
    return DEFAULT_COOLDOWN_ACTION_TYPES


def _manual_contact_actions(policy: MerchantPolicyConfig) -> frozenset[RecoveryActionType]:
    if policy.manual_contact_approval_action_types:
        return policy.manual_contact_approval_action_types
    return DEFAULT_MANUAL_CONTACT_APPROVAL_ACTION_TYPES


def _attempt_cap_applies(context: PolicyEvaluationContext, action: RecoveryActionType) -> bool:
    if action not in RECOVERY_INTERVENTION_ACTION_TYPES:
        return False
    if action == RecoveryActionType.WAIT and context.provider_retries_active:
        return False
    return True


def evaluate_policy(
    context: PolicyEvaluationContext,
    policy: MerchantPolicyConfig,
) -> PolicyDecision:
    if context.action_type == RecoveryActionType.STOP:
        return _evaluate_stop_policy(context, policy)
    return _evaluate_intervention_policy(context, policy)


def _evaluate_stop_policy(
    context: PolicyEvaluationContext,
    policy: MerchantPolicyConfig,
) -> PolicyDecision:
    reasons: list[PolicyReasonCode] = []

    if context.case_terminal:
        reasons.append(PolicyReasonCode.CASE_TERMINAL)

    if context.provider_success_known:
        reasons.append(PolicyReasonCode.PROVIDER_SUCCESS_ALREADY_KNOWN)

    combined = sort_policy_reasons(reasons)
    eligible = not any(reason in HARD_BLOCK_REASON_CODES for reason in combined)
    return PolicyDecision(
        eligible=eligible,
        requires_approval=False,
        reasons=tuple(combined),
    )


def _evaluate_intervention_policy(
    context: PolicyEvaluationContext,
    policy: MerchantPolicyConfig,
) -> PolicyDecision:
    reasons: list[PolicyReasonCode] = []
    approval_reasons: list[PolicyReasonCode] = []

    action = context.action_type
    contact_actions = _contact_action_types(policy)
    cooldown_actions = _cooldown_action_types(policy)

    if context.case_terminal:
        reasons.append(PolicyReasonCode.CASE_TERMINAL)

    if context.provider_success_known:
        reasons.append(PolicyReasonCode.PROVIDER_SUCCESS_ALREADY_KNOWN)

    if action not in policy.allowed_action_types:
        reasons.append(PolicyReasonCode.ACTION_NOT_ALLOWED)

    if (
        _attempt_cap_applies(context, action)
        and context.recovery_attempts_so_far >= policy.max_recovery_attempts
    ):
        reasons.append(PolicyReasonCode.MAX_RECOVERY_ATTEMPTS_REACHED)

    if action in contact_actions and context.contacts_last_24h >= policy.max_contacts_per_24h:
        reasons.append(PolicyReasonCode.CONTACT_CAP_REACHED)

    if action == RecoveryActionType.RETRY_SAME_METHOD and context.verified_rail_downtime:
        reasons.append(PolicyReasonCode.RAIL_DOWNTIME_RETRY_BLOCKED)

    if action in context.equivalent_actions_in_flight:
        reasons.append(PolicyReasonCode.EQUIVALENT_ACTION_IN_FLIGHT)

    if (
        action in PAYMENT_LINK_MECHANISM_ACTIONS
        and not context.payment_link_data_sufficient
    ):
        reasons.append(PolicyReasonCode.PAYMENT_LINK_DATA_INSUFFICIENT)

    if context.auto_execution_requested and not policy.automation_enabled:
        reasons.append(PolicyReasonCode.AUTOMATION_DISABLED)

    if action in cooldown_actions and _is_cooldown_active(context, policy):
        reasons.append(PolicyReasonCode.COOLDOWN_ACTIVE)

    if context.amount_at_risk_minor > policy.auto_action_limit_minor:
        approval_reasons.append(PolicyReasonCode.AMOUNT_ABOVE_AUTO_ACTION_LIMIT)

    if context.confidence < policy.minimum_auto_confidence:
        approval_reasons.append(PolicyReasonCode.CONFIDENCE_BELOW_AUTO_THRESHOLD)

    if action in policy.approval_only_action_types:
        approval_reasons.append(PolicyReasonCode.ACTION_REQUIRES_APPROVAL)

    if action in _manual_contact_actions(policy):
        approval_reasons.append(PolicyReasonCode.MANUAL_CONTACT_APPROVAL_REQUIRED)

    hard_blocked = any(reason in HARD_BLOCK_REASON_CODES for reason in reasons)
    requires_approval = bool(approval_reasons)

    combined = sort_policy_reasons(reasons + approval_reasons)
    eligible = not hard_blocked

    return PolicyDecision(
        eligible=eligible,
        requires_approval=requires_approval,
        reasons=tuple(combined),
    )
