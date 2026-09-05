"""One construction of the policy question the executor will actually ask.

WHY THIS MODULE EXISTS

`requires_approval` and `policy_eligible` exist twice for every recommendation,
and they are not the same fact:

* the values persisted on `recovery_recommendations` are what the policy engine
  decided *when the analysis ran*. They are a historical record and must not be
  rewritten;
* the branch `create_case_action` takes -- execute now, or file an approval
  request -- comes from re-evaluating policy *at submit time*, against the case
  as it stands now.

The case detail response used to show the first and the executor used the
second, so the UI could promise "this will execute immediately" and the
executor could file an approval request instead. On the demo dataset seeded
before recommendations were produced by real inference, those two verdicts
disagreed on 10 of the 15 executable cases -- every one of them in that
direction.

Both paths now build the context here, so the verdict the UI shows is the
verdict the executor will reach. The stored per-candidate flags stay exactly as
they were: they are the audit record of the analysis, not a prediction of what
the executor will do.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import PAYMENT_LINK_MECHANISM_ACTIONS, RecoveryActionType
from app.models.merchant_policy import MerchantPolicy
from app.models.recovery_case import RecoveryCase
from app.models.recovery_recommendation import RecoveryRecommendation
from app.policies.engine import evaluate_policy
from app.policies.schemas import (
    MerchantPolicyConfig,
    PolicyDecision,
    PolicyEvaluationContext,
)
from app.recovery.service import merchant_policy_from_model


def build_execution_policy_context(
    *,
    case: RecoveryCase,
    recommendation: RecoveryRecommendation,
    recovery_attempts_so_far: int,
    payment_link_action_in_flight: bool,
    auto_execute: bool,
) -> PolicyEvaluationContext:
    """The context the executor evaluates before choosing an execution branch."""
    in_flight: frozenset[RecoveryActionType] = frozenset()
    if payment_link_action_in_flight:
        # Any payment-link-mechanism action in flight blocks every other
        # candidate that shares the mechanism, regardless of which one is
        # actually blocking -- they would collide on the same Payment Link
        # creation call for this case.
        in_flight = frozenset(PAYMENT_LINK_MECHANISM_ACTIONS)
    return PolicyEvaluationContext(
        action_type=RecoveryActionType(recommendation.action_type),
        amount_at_risk_minor=case.amount_at_risk_minor,
        recovery_attempts_so_far=recovery_attempts_so_far,
        contacts_last_24h=0,
        confidence=recommendation.confidence,
        expected_value_minor=recommendation.expected_value_minor,
        payment_link_data_sufficient=case.amount_at_risk_minor > 0 and bool(case.currency),
        case_terminal=False,
        provider_success_known=False,
        equivalent_actions_in_flight=in_flight,
        auto_execution_requested=auto_execute,
        cooldown_elapsed_minutes=999,
    )


def load_merchant_policy(session: Session, organization_id) -> MerchantPolicyConfig | None:
    row = session.execute(
        select(MerchantPolicy).where(MerchantPolicy.organization_id == organization_id)
    ).scalar_one_or_none()
    return None if row is None else merchant_policy_from_model(row)


def evaluate_execution_policy(
    session: Session,
    *,
    case: RecoveryCase,
    recommendation: RecoveryRecommendation,
    auto_execute: bool,
) -> PolicyDecision | None:
    """Re-run the executor's policy question from a read-only caller.

    Returns `None` when the organization has no policy row. The executor treats
    that as a hard block, but a read path must not turn a missing policy into a
    failed page load: the caller falls back to the stored analysis-time verdict
    and shows nothing new.
    """
    # Imported here: app.actions.repository imports this module's siblings, and
    # a module-level import would close a cycle through app.actions.service.
    from app.actions.repository import RecoveryActionRepository

    policy = load_merchant_policy(session, case.organization_id)
    if policy is None:
        return None
    repo = RecoveryActionRepository(session)
    blocking = repo.get_blocking_payment_link_action(
        case_id=case.id, organization_id=case.organization_id
    )
    context = build_execution_policy_context(
        case=case,
        recommendation=recommendation,
        recovery_attempts_so_far=repo.count_actions(
            case_id=case.id, organization_id=case.organization_id
        ),
        payment_link_action_in_flight=blocking is not None,
        auto_execute=auto_execute,
    )
    return evaluate_policy(context, policy)
