"""Stable deterministic policy reason codes."""

from enum import Enum


class PolicyReasonCode(str, Enum):
    ACTION_NOT_ALLOWED = "ACTION_NOT_ALLOWED"
    MAX_RECOVERY_ATTEMPTS_REACHED = "MAX_RECOVERY_ATTEMPTS_REACHED"
    CONTACT_CAP_REACHED = "CONTACT_CAP_REACHED"
    RAIL_DOWNTIME_RETRY_BLOCKED = "RAIL_DOWNTIME_RETRY_BLOCKED"
    EQUIVALENT_ACTION_IN_FLIGHT = "EQUIVALENT_ACTION_IN_FLIGHT"
    CASE_TERMINAL = "CASE_TERMINAL"
    PROVIDER_SUCCESS_ALREADY_KNOWN = "PROVIDER_SUCCESS_ALREADY_KNOWN"
    PAYMENT_LINK_DATA_INSUFFICIENT = "PAYMENT_LINK_DATA_INSUFFICIENT"
    AUTOMATION_DISABLED = "AUTOMATION_DISABLED"
    COOLDOWN_ACTIVE = "COOLDOWN_ACTIVE"
    AMOUNT_ABOVE_AUTO_ACTION_LIMIT = "AMOUNT_ABOVE_AUTO_ACTION_LIMIT"
    CONFIDENCE_BELOW_AUTO_THRESHOLD = "CONFIDENCE_BELOW_AUTO_THRESHOLD"
    ACTION_REQUIRES_APPROVAL = "ACTION_REQUIRES_APPROVAL"
    MANUAL_CONTACT_APPROVAL_REQUIRED = "MANUAL_CONTACT_APPROVAL_REQUIRED"


APPROVAL_REASON_CODES: frozenset[PolicyReasonCode] = frozenset(
    {
        PolicyReasonCode.AMOUNT_ABOVE_AUTO_ACTION_LIMIT,
        PolicyReasonCode.CONFIDENCE_BELOW_AUTO_THRESHOLD,
        PolicyReasonCode.ACTION_REQUIRES_APPROVAL,
        PolicyReasonCode.MANUAL_CONTACT_APPROVAL_REQUIRED,
    }
)

HARD_BLOCK_REASON_CODES: frozenset[PolicyReasonCode] = frozenset(
    {
        PolicyReasonCode.ACTION_NOT_ALLOWED,
        PolicyReasonCode.MAX_RECOVERY_ATTEMPTS_REACHED,
        PolicyReasonCode.CONTACT_CAP_REACHED,
        PolicyReasonCode.RAIL_DOWNTIME_RETRY_BLOCKED,
        PolicyReasonCode.EQUIVALENT_ACTION_IN_FLIGHT,
        PolicyReasonCode.CASE_TERMINAL,
        PolicyReasonCode.PROVIDER_SUCCESS_ALREADY_KNOWN,
        PolicyReasonCode.PAYMENT_LINK_DATA_INSUFFICIENT,
        PolicyReasonCode.AUTOMATION_DISABLED,
        PolicyReasonCode.COOLDOWN_ACTIVE,
    }
)

REASON_CODE_SORT_ORDER: tuple[PolicyReasonCode, ...] = tuple(PolicyReasonCode)


def sort_policy_reasons(reasons: list[PolicyReasonCode]) -> list[PolicyReasonCode]:
    order = {code: index for index, code in enumerate(REASON_CODE_SORT_ORDER)}
    unique = list(dict.fromkeys(reasons))
    return sorted(unique, key=lambda code: order[code])
