"""Deterministic candidate ranking and STOP selection."""

from __future__ import annotations

from app.domain.enums import RecoveryActionType
from app.recovery.candidates import ACTION_PRIORITY
from app.recovery.schemas import RankedRecommendationCandidate, RecommendationCandidate

# P0 heuristic operational/contact burden mapping; lower is better.
OPERATIONAL_BURDEN: dict[RecoveryActionType, int] = {
    RecoveryActionType.WAIT: 0,
    RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD: 1,
    RecoveryActionType.CREATE_PAYMENT_LINK: 2,
    RecoveryActionType.RETRY_SAME_METHOD: 3,
    RecoveryActionType.SEND_RECOVERY_MESSAGE: 4,
    RecoveryActionType.ESCALATE_TO_HUMAN: 5,
    RecoveryActionType.STOP: 6,
}

_ACTION_PRIORITY_INDEX = {action: index for index, action in enumerate(ACTION_PRIORITY)}


def _rank_sort_key(candidate: RecommendationCandidate) -> tuple:
    eligible_rank = 0 if candidate.eligible else 1
    burden = candidate.operational_burden
    action_priority = _ACTION_PRIORITY_INDEX[candidate.action_type]
    return (
        eligible_rank,
        -candidate.expected_value_minor,
        -candidate.success_probability,
        burden,
        action_priority,
    )


def rank_candidates(
    candidates: list[RecommendationCandidate],
) -> list[RankedRecommendationCandidate]:
    ordered = sorted(candidates, key=_rank_sort_key)
    ranked: list[RankedRecommendationCandidate] = []
    for index, candidate in enumerate(ordered, start=1):
        ranked.append(
            RankedRecommendationCandidate(
                **candidate.model_dump(),
                rank=index,
            )
        )
    return ranked


def select_recommendation(
    ranked_candidates: list[RankedRecommendationCandidate],
) -> RankedRecommendationCandidate | None:
    """Select the highest-ranked eligible recommendation, or None if none exist."""
    eligible_non_stop = [
        candidate
        for candidate in ranked_candidates
        if candidate.eligible and candidate.action_type != RecoveryActionType.STOP
    ]

    positive = [
        candidate for candidate in eligible_non_stop if candidate.expected_value_minor > 0
    ]
    if positive:
        selected = positive[0]
        if not selected.eligible:
            raise ValueError("Selection invariant violated: chosen candidate is ineligible.")
        return selected

    stop_candidates = [
        candidate
        for candidate in ranked_candidates
        if candidate.action_type == RecoveryActionType.STOP and candidate.eligible
    ]
    if stop_candidates:
        return stop_candidates[0]

    return None
