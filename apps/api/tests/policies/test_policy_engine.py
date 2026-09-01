"""Policy engine tests."""

from __future__ import annotations

from decimal import Decimal

from app.domain.enums import RecoveryActionType
from app.policies.engine import evaluate_policy
from app.policies.reason_codes import PolicyReasonCode
from app.policies.schemas import MerchantPolicyConfig, PolicyEvaluationContext

BASE_POLICY = MerchantPolicyConfig(
    auto_action_limit_minor=1_000_000,
    max_recovery_attempts=3,
    max_contacts_per_24h=2,
    minimum_auto_confidence=Decimal("0.70"),
    cooldown_minutes=30,
    automation_enabled=True,
    allowed_action_types=frozenset(RecoveryActionType),
)


def _context(**overrides) -> PolicyEvaluationContext:
    base = {
        "action_type": RecoveryActionType.WAIT,
        "amount_at_risk_minor": 500_000,
        "recovery_attempts_so_far": 0,
        "contacts_last_24h": 0,
        "confidence": Decimal("0.80"),
        "expected_value_minor": 100,
        "payment_link_data_sufficient": True,
        "case_terminal": False,
        "provider_success_known": False,
        "verified_rail_downtime": False,
        "equivalent_actions_in_flight": frozenset(),
        "auto_execution_requested": False,
        "cooldown_elapsed_minutes": None,
        "provider_retries_active": False,
    }
    base.update(overrides)
    return PolicyEvaluationContext(**base)


def test_action_not_in_allowlist_is_blocked() -> None:
    policy = BASE_POLICY.model_copy(
        update={
            "allowed_action_types": frozenset(
                {RecoveryActionType.WAIT, RecoveryActionType.STOP}
            )
        }
    )
    decision = evaluate_policy(
        _context(action_type=RecoveryActionType.CREATE_PAYMENT_LINK),
        policy,
    )
    assert decision.eligible is False
    assert PolicyReasonCode.ACTION_NOT_ALLOWED in decision.reasons


def test_max_recovery_attempts_reached_for_business_intervention() -> None:
    decision = evaluate_policy(
        _context(
            action_type=RecoveryActionType.CREATE_PAYMENT_LINK,
            recovery_attempts_so_far=3,
        ),
        BASE_POLICY,
    )
    assert decision.eligible is False
    assert PolicyReasonCode.MAX_RECOVERY_ATTEMPTS_REACHED in decision.reasons


def test_provider_retry_wait_survives_attempt_cap() -> None:
    decision = evaluate_policy(
        _context(
            action_type=RecoveryActionType.WAIT,
            recovery_attempts_so_far=3,
            provider_retries_active=True,
        ),
        BASE_POLICY,
    )
    assert decision.eligible is True
    assert PolicyReasonCode.MAX_RECOVERY_ATTEMPTS_REACHED not in decision.reasons


def test_contact_cap_reached() -> None:
    decision = evaluate_policy(
        _context(
            action_type=RecoveryActionType.SEND_RECOVERY_MESSAGE,
            contacts_last_24h=2,
        ),
        BASE_POLICY,
    )
    assert decision.eligible is False
    assert PolicyReasonCode.CONTACT_CAP_REACHED in decision.reasons


def test_verified_downtime_blocks_retry_same_method() -> None:
    decision = evaluate_policy(
        _context(
            action_type=RecoveryActionType.RETRY_SAME_METHOD,
            verified_rail_downtime=True,
        ),
        BASE_POLICY,
    )
    assert decision.eligible is False
    assert PolicyReasonCode.RAIL_DOWNTIME_RETRY_BLOCKED in decision.reasons


def test_equivalent_action_in_flight_blocks() -> None:
    decision = evaluate_policy(
        _context(
            action_type=RecoveryActionType.CREATE_PAYMENT_LINK,
            equivalent_actions_in_flight=frozenset({RecoveryActionType.CREATE_PAYMENT_LINK}),
        ),
        BASE_POLICY,
    )
    assert decision.eligible is False
    assert PolicyReasonCode.EQUIVALENT_ACTION_IN_FLIGHT in decision.reasons


def test_terminal_case_blocks() -> None:
    decision = evaluate_policy(_context(case_terminal=True), BASE_POLICY)
    assert decision.eligible is False
    assert PolicyReasonCode.CASE_TERMINAL in decision.reasons


def test_provider_success_already_known_blocks() -> None:
    decision = evaluate_policy(_context(provider_success_known=True), BASE_POLICY)
    assert decision.eligible is False
    assert PolicyReasonCode.PROVIDER_SUCCESS_ALREADY_KNOWN in decision.reasons


def test_payment_link_data_insufficient_blocks() -> None:
    decision = evaluate_policy(
        _context(
            action_type=RecoveryActionType.CREATE_PAYMENT_LINK,
            payment_link_data_sufficient=False,
        ),
        BASE_POLICY,
    )
    assert decision.eligible is False
    assert PolicyReasonCode.PAYMENT_LINK_DATA_INSUFFICIENT in decision.reasons


def test_automation_disabled_blocks_auto_execution() -> None:
    policy = BASE_POLICY.model_copy(update={"automation_enabled": False})
    decision = evaluate_policy(
        _context(auto_execution_requested=True),
        policy,
    )
    assert decision.eligible is False
    assert PolicyReasonCode.AUTOMATION_DISABLED in decision.reasons


def test_cooldown_active_blocks_retry_like_action() -> None:
    decision = evaluate_policy(
        _context(
            action_type=RecoveryActionType.RETRY_SAME_METHOD,
            cooldown_elapsed_minutes=29,
        ),
        BASE_POLICY,
    )
    assert decision.eligible is False
    assert PolicyReasonCode.COOLDOWN_ACTIVE in decision.reasons


def test_cooldown_expired_at_exact_boundary() -> None:
    decision = evaluate_policy(
        _context(
            action_type=RecoveryActionType.RETRY_SAME_METHOD,
            cooldown_elapsed_minutes=30,
        ),
        BASE_POLICY,
    )
    assert decision.eligible is True
    assert PolicyReasonCode.COOLDOWN_ACTIVE not in decision.reasons


def test_amount_above_auto_limit_requires_approval_but_stays_eligible() -> None:
    decision = evaluate_policy(
        _context(amount_at_risk_minor=1_000_001),
        BASE_POLICY,
    )
    assert decision.eligible is True
    assert decision.requires_approval is True
    assert PolicyReasonCode.AMOUNT_ABOVE_AUTO_ACTION_LIMIT in decision.reasons


def test_amount_equal_auto_limit_does_not_require_amount_approval() -> None:
    decision = evaluate_policy(
        _context(amount_at_risk_minor=1_000_000),
        BASE_POLICY,
    )
    assert PolicyReasonCode.AMOUNT_ABOVE_AUTO_ACTION_LIMIT not in decision.reasons


def test_low_confidence_requires_approval() -> None:
    decision = evaluate_policy(
        _context(confidence=Decimal("0.50")),
        BASE_POLICY,
    )
    assert decision.eligible is True
    assert decision.requires_approval is True
    assert PolicyReasonCode.CONFIDENCE_BELOW_AUTO_THRESHOLD in decision.reasons


def test_hard_block_with_approval_condition_remains_ineligible() -> None:
    decision = evaluate_policy(
        _context(
            action_type=RecoveryActionType.CREATE_PAYMENT_LINK,
            amount_at_risk_minor=2_000_000,
            payment_link_data_sufficient=False,
        ),
        BASE_POLICY,
    )
    assert decision.eligible is False
    assert PolicyReasonCode.PAYMENT_LINK_DATA_INSUFFICIENT in decision.reasons
    assert PolicyReasonCode.AMOUNT_ABOVE_AUTO_ACTION_LIMIT in decision.reasons


def test_reasons_are_deterministic_and_deduplicated() -> None:
    decision = evaluate_policy(
        _context(
            action_type=RecoveryActionType.CREATE_PAYMENT_LINK,
            amount_at_risk_minor=2_000_000,
            confidence=Decimal("0.50"),
        ),
        BASE_POLICY.model_copy(
            update={
                "approval_only_action_types": frozenset(
                    {RecoveryActionType.CREATE_PAYMENT_LINK}
                )
            }
        ),
    )
    assert len(decision.reasons) == len(set(decision.reasons))
    assert list(decision.reasons) == sorted(
        decision.reasons,
        key=lambda code: list(PolicyReasonCode).index(code),
    )


def test_stop_does_not_require_allowlist_membership() -> None:
    policy = BASE_POLICY.model_copy(
        update={
            "allowed_action_types": frozenset(
                {
                    RecoveryActionType.WAIT,
                    RecoveryActionType.CREATE_PAYMENT_LINK,
                }
            )
        }
    )
    decision = evaluate_policy(_context(action_type=RecoveryActionType.STOP), policy)
    assert decision.eligible is True
    assert decision.requires_approval is False
    assert PolicyReasonCode.ACTION_NOT_ALLOWED not in decision.reasons


def test_empty_intervention_allowlist_still_permits_stop() -> None:
    policy = BASE_POLICY.model_copy(update={"allowed_action_types": frozenset()})
    decision = evaluate_policy(_context(action_type=RecoveryActionType.STOP), policy)
    assert decision.eligible is True
    assert decision.requires_approval is False


def test_non_stop_action_still_obey_allowlist() -> None:
    policy = BASE_POLICY.model_copy(
        update={"allowed_action_types": frozenset({RecoveryActionType.WAIT})}
    )
    decision = evaluate_policy(
        _context(action_type=RecoveryActionType.CREATE_PAYMENT_LINK),
        policy,
    )
    assert decision.eligible is False
    assert PolicyReasonCode.ACTION_NOT_ALLOWED in decision.reasons


def test_stop_blocked_when_provider_success_known_even_without_allowlist() -> None:
    policy = BASE_POLICY.model_copy(update={"allowed_action_types": frozenset()})
    decision = evaluate_policy(
        _context(
            action_type=RecoveryActionType.STOP,
            provider_success_known=True,
        ),
        policy,
    )
    assert decision.eligible is False
    assert PolicyReasonCode.PROVIDER_SUCCESS_ALREADY_KNOWN in decision.reasons


def test_stop_blocked_when_terminal_even_without_allowlist() -> None:
    policy = BASE_POLICY.model_copy(update={"allowed_action_types": frozenset()})
    decision = evaluate_policy(
        _context(action_type=RecoveryActionType.STOP, case_terminal=True),
        policy,
    )
    assert decision.eligible is False
    assert PolicyReasonCode.CASE_TERMINAL in decision.reasons
