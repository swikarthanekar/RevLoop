"""Prompt 09 final hardening regression tests."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain.enums import CaseType, FailureCategory, RecoveryActionType
from app.ml.fallback import (
    FALLBACK_MODEL_VERSION,
    get_fallback_probability,
    iter_supported_candidate_contexts,
)
from app.policies.engine import evaluate_policy
from app.policies.reason_codes import PolicyReasonCode
from app.policies.schemas import MerchantPolicyConfig, PolicyEvaluationContext
from app.recovery.candidates import generate_candidates
from app.recovery.erv import calculate_fatigue_penalty
from app.recovery.ranking import rank_candidates, select_recommendation
from app.recovery.schemas import CandidateGenerationContext, RecommendationCandidate

BASE_POLICY = MerchantPolicyConfig(
    auto_action_limit_minor=1_000_000,
    max_recovery_attempts=3,
    max_contacts_per_24h=2,
    minimum_auto_confidence=Decimal("0.70"),
    cooldown_minutes=30,
    automation_enabled=True,
    allowed_action_types=frozenset(RecoveryActionType),
)


def _policy_context(**overrides) -> PolicyEvaluationContext:
    base = {
        "action_type": RecoveryActionType.WAIT,
        "amount_at_risk_minor": 500_000,
        "recovery_attempts_so_far": 3,
        "contacts_last_24h": 2,
        "confidence": Decimal("0.50"),
        "expected_value_minor": 100,
        "payment_link_data_sufficient": True,
        "case_terminal": False,
        "provider_success_known": False,
        "verified_rail_downtime": False,
        "equivalent_actions_in_flight": frozenset(),
        "auto_execution_requested": False,
        "cooldown_elapsed_minutes": 10,
        "provider_retries_active": False,
    }
    base.update(overrides)
    return PolicyEvaluationContext(**base)


def _candidate(
    action: RecoveryActionType,
    *,
    erv: int,
    eligible: bool = True,
    requires_approval: bool = False,
    probability: str = "0.60",
    burden: int = 1,
) -> RecommendationCandidate:
    return RecommendationCandidate(
        action_type=action,
        success_probability=Decimal(probability),
        expected_recovered_minor=max(erv, 0),
        expected_value_minor=erv,
        confidence=Decimal("0.80"),
        eligible=eligible,
        requires_approval=requires_approval,
        operational_burden=burden,
    )


@pytest.mark.parametrize(
    "failure_category",
    [
        FailureCategory.TECHNICAL_FAILURE,
        FailureCategory.INSUFFICIENT_FUNDS,
        FailureCategory.AUTHENTICATION_FAILURE,
    ],
)
def test_active_downtime_dominates_failure_category_matrix(
    failure_category: FailureCategory,
) -> None:
    context = CandidateGenerationContext(
        failure_category=failure_category,
        case_type=CaseType.PAYMENT_FAILURE,
        active_payment_rail_downtime=True,
    )
    assert generate_candidates(context) == (
        RecoveryActionType.WAIT,
        RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD,
        RecoveryActionType.CREATE_PAYMENT_LINK,
        RecoveryActionType.STOP,
    )
    for action in generate_candidates(context):
        probability = get_fallback_probability(context, action)
        assert isinstance(probability, Decimal)
        assert Decimal("0") <= probability <= Decimal("1")


def test_subscription_pending_active_downtime_uses_downtime_matrix_and_fallback() -> None:
    context = CandidateGenerationContext(
        failure_category=FailureCategory.MANDATE_OR_RECURRING_FAILURE,
        case_type=CaseType.SUBSCRIPTION_FAILURE,
        subscription_status="pending",
        provider_retries_active=True,
        active_payment_rail_downtime=True,
    )
    candidates = generate_candidates(context)
    assert candidates == (
        RecoveryActionType.WAIT,
        RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD,
        RecoveryActionType.CREATE_PAYMENT_LINK,
        RecoveryActionType.STOP,
    )
    assert get_fallback_probability(context, RecoveryActionType.CREATE_PAYMENT_LINK) == Decimal(
        "0.65"
    )


def test_subscription_halted_active_downtime_uses_downtime_matrix_and_fallback() -> None:
    context = CandidateGenerationContext(
        failure_category=FailureCategory.MANDATE_OR_RECURRING_FAILURE,
        case_type=CaseType.SUBSCRIPTION_FAILURE,
        subscription_status="halted",
        active_payment_rail_downtime=True,
    )
    candidates = generate_candidates(context)
    assert RecoveryActionType.ESCALATE_TO_HUMAN not in candidates
    assert get_fallback_probability(context, RecoveryActionType.CREATE_PAYMENT_LINK) == Decimal(
        "0.65"
    )


def test_unknown_subscription_substate_uses_conservative_recurring_fallback() -> None:
    context = CandidateGenerationContext(
        failure_category=FailureCategory.TECHNICAL_FAILURE,
        case_type=CaseType.SUBSCRIPTION_FAILURE,
        subscription_status="active",
    )
    assert generate_candidates(context) == (
        RecoveryActionType.WAIT,
        RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD,
        RecoveryActionType.SEND_RECOVERY_MESSAGE,
        RecoveryActionType.STOP,
    )
    assert RecoveryActionType.RETRY_SAME_METHOD not in generate_candidates(context)


def test_payment_failure_rejects_subscription_only_fields() -> None:
    with pytest.raises(ValidationError):
        CandidateGenerationContext(
            failure_category=FailureCategory.INSUFFICIENT_FUNDS,
            case_type=CaseType.PAYMENT_FAILURE,
            subscription_status="pending",
        )


def test_every_generated_candidate_has_fallback_probability() -> None:
    for context in iter_supported_candidate_contexts():
        for action in generate_candidates(context):
            probability = get_fallback_probability(context, action)
            assert isinstance(probability, Decimal)
            assert Decimal("0") <= probability <= Decimal("1")
            if action == RecoveryActionType.STOP:
                assert probability == Decimal("0")


def test_provider_success_known_does_not_select_stop() -> None:
    ranked = rank_candidates(
        [
            _candidate(RecoveryActionType.CREATE_PAYMENT_LINK, erv=500, eligible=False),
            _candidate(RecoveryActionType.STOP, erv=0, eligible=False),
        ]
    )
    assert select_recommendation(ranked) is None


def test_terminal_case_does_not_select_any_action() -> None:
    ranked = rank_candidates(
        [
            _candidate(RecoveryActionType.WAIT, erv=100, eligible=False),
            _candidate(RecoveryActionType.STOP, erv=0, eligible=False),
        ]
    )
    assert select_recommendation(ranked) is None


def test_all_interventions_blocked_eligible_stop_selects_stop() -> None:
    ranked = rank_candidates(
        [
            _candidate(RecoveryActionType.CREATE_PAYMENT_LINK, erv=900, eligible=False),
            _candidate(RecoveryActionType.STOP, erv=0, eligible=True),
        ]
    )
    selected = select_recommendation(ranked)
    assert selected is not None
    assert selected.action_type == RecoveryActionType.STOP
    assert selected.eligible is True


def test_all_interventions_blocked_ineligible_stop_selects_nothing() -> None:
    ranked = rank_candidates(
        [
            _candidate(RecoveryActionType.CREATE_PAYMENT_LINK, erv=900, eligible=False),
            _candidate(RecoveryActionType.STOP, erv=0, eligible=False),
        ]
    )
    assert select_recommendation(ranked) is None


def test_selection_never_returns_ineligible_candidate() -> None:
    ranked = rank_candidates(
        [
            _candidate(RecoveryActionType.WAIT, erv=100, eligible=True),
            _candidate(RecoveryActionType.STOP, erv=0, eligible=True),
        ]
    )
    selected = select_recommendation(ranked)
    assert selected is not None
    assert selected.eligible is True


def test_provider_retry_wait_not_blocked_by_attempt_cap() -> None:
    decision = evaluate_policy(
        _policy_context(
            action_type=RecoveryActionType.WAIT,
            provider_retries_active=True,
        ),
        BASE_POLICY,
    )
    assert decision.eligible is True
    assert PolicyReasonCode.MAX_RECOVERY_ATTEMPTS_REACHED not in decision.reasons


def test_business_intervention_still_blocked_by_attempt_cap() -> None:
    decision = evaluate_policy(
        _policy_context(action_type=RecoveryActionType.CREATE_PAYMENT_LINK),
        BASE_POLICY,
    )
    assert decision.eligible is False
    assert PolicyReasonCode.MAX_RECOVERY_ATTEMPTS_REACHED in decision.reasons


def test_send_recovery_message_contact_capped() -> None:
    decision = evaluate_policy(
        _policy_context(action_type=RecoveryActionType.SEND_RECOVERY_MESSAGE),
        BASE_POLICY,
    )
    assert PolicyReasonCode.CONTACT_CAP_REACHED in decision.reasons


def test_escalate_not_contact_capped_by_default() -> None:
    decision = evaluate_policy(
        _policy_context(action_type=RecoveryActionType.ESCALATE_TO_HUMAN),
        BASE_POLICY,
    )
    assert PolicyReasonCode.CONTACT_CAP_REACHED not in decision.reasons


def test_fatigue_applies_to_message_not_escalation() -> None:
    assert calculate_fatigue_penalty(
        action=RecoveryActionType.SEND_RECOVERY_MESSAGE,
        contacts_last_24h=1,
    ) > 0
    assert calculate_fatigue_penalty(
        action=RecoveryActionType.ESCALATE_TO_HUMAN,
        contacts_last_24h=1,
    ) == 0


def test_cooldown_blocks_retry_and_message_not_escalation() -> None:
    retry = evaluate_policy(
        _policy_context(action_type=RecoveryActionType.RETRY_SAME_METHOD),
        BASE_POLICY,
    )
    message = evaluate_policy(
        _policy_context(action_type=RecoveryActionType.SEND_RECOVERY_MESSAGE),
        BASE_POLICY,
    )
    escalate = evaluate_policy(
        _policy_context(action_type=RecoveryActionType.ESCALATE_TO_HUMAN),
        BASE_POLICY,
    )
    assert PolicyReasonCode.COOLDOWN_ACTIVE in retry.reasons
    assert PolicyReasonCode.COOLDOWN_ACTIVE in message.reasons
    assert PolicyReasonCode.COOLDOWN_ACTIVE not in escalate.reasons


def test_cooldown_expires_at_exact_boundary() -> None:
    decision = evaluate_policy(
        _policy_context(
            action_type=RecoveryActionType.RETRY_SAME_METHOD,
            cooldown_elapsed_minutes=30,
        ),
        BASE_POLICY,
    )
    assert PolicyReasonCode.COOLDOWN_ACTIVE not in decision.reasons


def test_stop_not_amount_or_confidence_approval_required() -> None:
    decision = evaluate_policy(
        _policy_context(
            action_type=RecoveryActionType.STOP,
            amount_at_risk_minor=5_000_000,
            confidence=Decimal("0.10"),
            recovery_attempts_so_far=99,
            contacts_last_24h=99,
            cooldown_elapsed_minutes=0,
        ),
        BASE_POLICY,
    )
    assert decision.eligible is True
    assert decision.requires_approval is False
    assert PolicyReasonCode.AMOUNT_ABOVE_AUTO_ACTION_LIMIT not in decision.reasons
    assert PolicyReasonCode.CONFIDENCE_BELOW_AUTO_THRESHOLD not in decision.reasons


def test_complete_ranking_tie_uses_fixed_action_priority() -> None:
    ranked = rank_candidates(
        [
            _candidate(
                RecoveryActionType.CREATE_PAYMENT_LINK,
                erv=200,
                probability="0.70",
                burden=1,
            ),
            _candidate(
                RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD,
                erv=200,
                probability="0.70",
                burden=1,
            ),
        ]
    )
    assert ranked[0].action_type == RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD


def test_fallback_model_version_unchanged() -> None:
    assert FALLBACK_MODEL_VERSION == "heuristic_fallback_v1"


def test_allowlist_exhaustion_still_selects_eligible_stop() -> None:
    ranked = rank_candidates(
        [
            _candidate(RecoveryActionType.WAIT, erv=500, eligible=False),
            _candidate(RecoveryActionType.CREATE_PAYMENT_LINK, erv=800, eligible=False),
            _candidate(RecoveryActionType.STOP, erv=0, eligible=True),
        ]
    )
    selected = select_recommendation(ranked)
    assert selected is not None
    assert selected.action_type == RecoveryActionType.STOP
    assert selected.eligible is True
