"""Score a hypothetical scenario through the production decision path.

WHY THIS IS NOT A SECOND ENGINE

Every step here is the same function the live analysis calls: `generate_candidates`,
`RecoveryPropensityModelService.score_actions`, `calculate_erv`,
`calculate_confidence`, `evaluate_policy`, `rank_candidates`,
`select_recommendation`. The only thing this module owns is the translation from
a request payload into the `RecoveryFeaturesV1` those functions expect.

That matters for what the simulator is for. If it ran a simplified copy of the
engine, moving a slider would demonstrate the copy, not the product. Because it
shares the implementation, a probability shown here is the probability the live
system would use for the same case.

WHY IT IS SAFE TO EXPOSE

Read-only by construction: it takes no case id, creates nothing, writes nothing,
and never touches a provider. The one database read is the merchant policy,
because the policy verdict has to reflect the merchant's real configuration
rather than a hardcoded stand-in -- otherwise the "requires approval" and
"blocked" outcomes would be theatre.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domain.capabilities import advisory_reason_text, execution_mode
from app.domain.enums import CaseType, FailureCategory
from app.ml.service import (
    ModelArtifactError,
    ModelInferenceError,
    RecoveryPropensityModelService,
)
from app.models.merchant_policy import MerchantPolicy
from app.policies.engine import evaluate_policy
from app.policies.schemas import PolicyEvaluationContext
from app.recovery.candidates import generate_candidates
from app.recovery.confidence import calculate_confidence
from app.recovery.erv import calculate_erv
from app.recovery.ranking import OPERATIONAL_BURDEN, rank_candidates, select_recommendation
from app.recovery.schemas import (
    CandidateGenerationContext,
    RecommendationCandidate,
    RecoveryFeaturesV1,
)
from app.recovery.service import merchant_policy_from_model
from app.schemas.simulator import (
    SimulatedCandidate,
    SimulationRequest,
    SimulationResponse,
)

#: The simulator only ever produces INR scenarios, matching the demo tenant.
SIMULATION_CURRENCY = "INR"


class SimulationUnavailableError(AppError):
    """The scenario could not be scored by the real model.

    Fails closed rather than falling back to a heuristic. A page whose whole
    claim is "these are the model's numbers" must not quietly show numbers a
    rule table produced.
    """

    def __init__(self, message: str) -> None:
        super().__init__(
            code="SIMULATION_UNAVAILABLE",
            message=message,
            status_code=503,
        )


def _feature_completeness(request: SimulationRequest) -> float:
    """Every simulated field is supplied, so completeness is total.

    Stated explicitly rather than passed as a magic 1.0: in the live path this
    is computed from which case fields were actually present, and a simulated
    scenario has all of them by construction.
    """
    return 1.0


def _evidence_strength(request: SimulationRequest) -> float:
    """How much the failure category is actually supported by evidence.

    Mirrors the live normalizer's behaviour: an explicitly-chosen category with
    a known payment method is strong evidence; `UNKNOWN` is weak.
    """
    if request.failure_category == FailureCategory.UNKNOWN:
        return 0.3
    if request.payment_method == "unknown":
        return 0.6
    return 0.9


def build_simulated_features(request: SimulationRequest) -> RecoveryFeaturesV1:
    """Translate a scenario into the model's feature vector.

    Derived fields use the same transforms as `build_recovery_features_v1`
    (`log1p` on money, a fixed clock) so the vector is indistinguishable from
    one the live path would produce for an equivalent case.
    """
    # A fixed reference clock keeps `hour_of_day` and `day_of_week` stable, so
    # the same scenario scores identically on every request. Without it a slider
    # the user did not touch would appear to change the answer.
    reference = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)

    return RecoveryFeaturesV1(
        amount_minor=request.amount_minor,
        amount_log1p=math.log1p(request.amount_minor),
        hours_since_failure=request.hours_since_failure,
        hour_of_day=reference.hour,
        day_of_week=reference.weekday(),
        customer_tenure_days=request.customer_tenure_days,
        successful_payments_90d=request.successful_payments_90d,
        failed_payments_30d=request.failed_payments_30d,
        payment_success_rate_90d=request.payment_success_rate_90d,
        historical_recovery_rate=None,
        historical_recovery_rate_missing=True,
        lifetime_value_minor=request.lifetime_value_minor,
        lifetime_value_log1p=math.log1p(request.lifetime_value_minor),
        retry_count_provider=request.retry_count_provider,
        recovery_attempts_so_far=request.recovery_attempts_so_far,
        contacts_last_24h=request.contacts_last_24h,
        rail_degraded=request.rail_degraded,
        same_method_recent_success=request.same_method_recent_success,
        alternate_method_recent_success=request.alternate_method_recent_success,
        is_subscription=request.case_type == CaseType.SUBSCRIPTION_FAILURE,
        case_type=request.case_type.value,
        failure_category=request.failure_category.value,
        payment_method=request.payment_method,
        customer_segment=request.customer_segment,
        downtime_severity="high" if request.rail_degraded else "none",
        feature_completeness=_feature_completeness(request),
        evidence_strength=_evidence_strength(request),
    )


def _candidate_context(request: SimulationRequest) -> CandidateGenerationContext:
    is_subscription = request.case_type == CaseType.SUBSCRIPTION_FAILURE
    return CandidateGenerationContext(
        failure_category=request.failure_category,
        case_type=request.case_type,
        # These two are only meaningful for a subscription; the context model
        # rejects them on a payment failure.
        subscription_status=request.subscription_status if is_subscription else None,
        provider_retries_active=request.provider_retries_active if is_subscription else False,
        uncertain_provider_state=False,
        active_payment_rail_downtime=request.rail_degraded,
        payment_link_data_sufficient=True,
    )


def _load_policy(session: Session, organization_id: UUID):
    policy = session.execute(
        select(MerchantPolicy).where(MerchantPolicy.organization_id == organization_id)
    ).scalar_one_or_none()
    if policy is None:
        raise SimulationUnavailableError("Merchant policy is not configured.")
    return merchant_policy_from_model(policy)


def simulate(
    session: Session,
    *,
    organization_id: UUID,
    request: SimulationRequest,
    propensity_model: RecoveryPropensityModelService | None = None,
) -> SimulationResponse:
    """Score `request` through the production decision path."""
    model = propensity_model or RecoveryPropensityModelService()
    policy = _load_policy(session, organization_id)
    context = _candidate_context(request)
    actions = list(generate_candidates(context))
    features = build_simulated_features(request)

    try:
        inference = model.score_actions(features=features, actions=actions)
    except (ModelArtifactError, ModelInferenceError) as exc:
        raise SimulationUnavailableError(
            "The recovery model could not score this scenario."
        ) from exc

    probability_by_action = {
        entry.action_type: Decimal(str(entry.probability)) for entry in inference.probabilities
    }

    candidates: list[RecommendationCandidate] = []
    for action in actions:
        probability = probability_by_action.get(action)
        if probability is None:  # pragma: no cover - defensive
            raise SimulationUnavailableError(
                f"The model returned no probability for {action.value}."
            )
        erv = calculate_erv(
            action=action,
            amount_at_risk_minor=request.amount_minor,
            success_probability=probability,
            contacts_last_24h=request.contacts_last_24h,
        )
        confidence = calculate_confidence(
            feature_completeness=features.feature_completeness,
            success_probability=probability,
            evidence_strength=features.evidence_strength,
        )
        decision = evaluate_policy(
            PolicyEvaluationContext(
                action_type=action,
                amount_at_risk_minor=request.amount_minor,
                recovery_attempts_so_far=request.recovery_attempts_so_far,
                contacts_last_24h=request.contacts_last_24h,
                confidence=confidence,
                expected_value_minor=erv.expected_value_minor,
                payment_link_data_sufficient=context.payment_link_data_sufficient,
                case_terminal=False,
                provider_success_known=False,
                verified_rail_downtime=request.rail_degraded,
                equivalent_actions_in_flight=frozenset(),
                auto_execution_requested=False,
                # No prior action exists in a hypothetical, so no cooldown is
                # running. Matches the live path's own placeholder.
                cooldown_elapsed_minutes=999,
                provider_retries_active=context.provider_retries_active,
            ),
            policy,
        )
        candidates.append(
            RecommendationCandidate(
                action_type=action,
                success_probability=probability,
                expected_recovered_minor=erv.expected_recovered_minor,
                expected_value_minor=erv.expected_value_minor,
                confidence=confidence,
                eligible=decision.eligible,
                requires_approval=decision.requires_approval,
                policy_reasons=tuple(reason.value for reason in decision.reasons),
                operational_burden=OPERATIONAL_BURDEN[action],
                execution_mode=execution_mode(action),
                action_cost_minor=erv.action_cost_minor,
                fatigue_penalty_minor=erv.fatigue_penalty_minor,
                operational_risk_penalty_minor=erv.operational_risk_penalty_minor,
                delay_penalty_minor=erv.delay_penalty_minor,
            )
        )

    ranked = rank_candidates(candidates)
    selected = select_recommendation(ranked)
    selected_action = selected.action_type if selected is not None else None

    return SimulationResponse(
        selected_action=selected_action.value if selected_action else None,
        top_ranked_action=ranked[0].action_type.value if ranked else None,
        candidates=[
            SimulatedCandidate(
                action_type=candidate.action_type.value,
                rank=candidate.rank,
                success_probability=float(candidate.success_probability),
                confidence=float(candidate.confidence),
                expected_recovered_minor=candidate.expected_recovered_minor,
                action_cost_minor=candidate.action_cost_minor,
                fatigue_penalty_minor=candidate.fatigue_penalty_minor,
                operational_risk_penalty_minor=candidate.operational_risk_penalty_minor,
                delay_penalty_minor=candidate.delay_penalty_minor,
                expected_value_minor=candidate.expected_value_minor,
                policy_eligible=candidate.eligible,
                requires_approval=candidate.requires_approval,
                policy_reasons=list(candidate.policy_reasons),
                execution_mode=candidate.execution_mode,
                advisory_reason=advisory_reason_text(candidate.action_type),
                selected=candidate.action_type == selected_action,
            )
            for candidate in ranked
        ],
        currency=SIMULATION_CURRENCY,
        amount_at_risk_minor=request.amount_minor,
        model_version=inference.model_version,
        model_family=inference.model_family,
        feature_schema_version=inference.feature_schema_version,
        inference_source=inference.source,
        policy_auto_action_limit_minor=policy.auto_action_limit_minor,
        policy_minimum_auto_confidence=float(policy.minimum_auto_confidence),
    )


__all__ = [
    "SIMULATION_CURRENCY",
    "SimulationUnavailableError",
    "build_simulated_features",
    "simulate",
]
