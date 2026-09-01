"""Ranking and STOP selection tests."""

from __future__ import annotations

from decimal import Decimal

from app.domain.enums import RecoveryActionType
from app.recovery.ranking import OPERATIONAL_BURDEN, rank_candidates, select_recommendation
from app.recovery.schemas import RecommendationCandidate


def _candidate(
    action: RecoveryActionType,
    *,
    erv: int,
    probability: str = "0.60",
    eligible: bool = True,
    requires_approval: bool = False,
) -> RecommendationCandidate:
    return RecommendationCandidate(
        action_type=action,
        success_probability=Decimal(probability),
        expected_recovered_minor=max(erv, 0),
        expected_value_minor=erv,
        confidence=Decimal("0.80"),
        eligible=eligible,
        requires_approval=requires_approval,
        operational_burden=OPERATIONAL_BURDEN[action],
    )


def test_highest_erv_wins_among_eligible() -> None:
    ranked = rank_candidates(
        [
            _candidate(RecoveryActionType.WAIT, erv=100),
            _candidate(RecoveryActionType.CREATE_PAYMENT_LINK, erv=500),
        ]
    )
    assert ranked[0].action_type == RecoveryActionType.CREATE_PAYMENT_LINK


def test_probability_breaks_equal_erv() -> None:
    ranked = rank_candidates(
        [
            _candidate(RecoveryActionType.WAIT, erv=200, probability="0.50"),
            _candidate(RecoveryActionType.CREATE_PAYMENT_LINK, erv=200, probability="0.80"),
        ]
    )
    assert ranked[0].action_type == RecoveryActionType.CREATE_PAYMENT_LINK


def test_burden_breaks_equal_erv_and_probability() -> None:
    ranked = rank_candidates(
        [
            _candidate(RecoveryActionType.SEND_RECOVERY_MESSAGE, erv=200, probability="0.70"),
            _candidate(RecoveryActionType.WAIT, erv=200, probability="0.70"),
        ]
    )
    assert ranked[0].action_type == RecoveryActionType.WAIT


def test_fixed_action_order_breaks_complete_tie() -> None:
    ranked = rank_candidates(
        [
            _candidate(RecoveryActionType.RETRY_SAME_METHOD, erv=200, probability="0.70"),
            _candidate(RecoveryActionType.WAIT, erv=200, probability="0.70"),
        ]
    )
    assert ranked[0].action_type == RecoveryActionType.WAIT


def test_eligible_candidates_sort_before_blocked() -> None:
    ranked = rank_candidates(
        [
            _candidate(RecoveryActionType.CREATE_PAYMENT_LINK, erv=900, eligible=False),
            _candidate(RecoveryActionType.WAIT, erv=100, eligible=True),
        ]
    )
    assert ranked[0].eligible is True
    assert ranked[-1].eligible is False


def test_blocked_candidate_is_preserved() -> None:
    ranked = rank_candidates(
        [
            _candidate(RecoveryActionType.CREATE_PAYMENT_LINK, erv=900, eligible=False),
            _candidate(RecoveryActionType.STOP, erv=0),
        ]
    )
    assert len(ranked) == 2
    assert any(not item.eligible for item in ranked)


def test_blocked_high_erv_action_cannot_be_selected() -> None:
    ranked = rank_candidates(
        [
            _candidate(RecoveryActionType.CREATE_PAYMENT_LINK, erv=900, eligible=False),
            _candidate(RecoveryActionType.WAIT, erv=50, eligible=True),
            _candidate(RecoveryActionType.STOP, erv=0, eligible=True),
        ]
    )
    selected = select_recommendation(ranked)
    assert selected is not None
    assert selected.action_type == RecoveryActionType.WAIT


def test_approval_required_eligible_action_can_be_selected() -> None:
    ranked = rank_candidates(
        [
            _candidate(
                RecoveryActionType.CREATE_PAYMENT_LINK,
                erv=500,
                eligible=True,
                requires_approval=True,
            ),
            _candidate(RecoveryActionType.STOP, erv=0, eligible=True),
        ]
    )
    selected = select_recommendation(ranked)
    assert selected is not None
    assert selected.action_type == RecoveryActionType.CREATE_PAYMENT_LINK
    assert selected.requires_approval is True


def test_select_stop_when_all_non_stop_erv_non_positive() -> None:
    ranked = rank_candidates(
        [
            _candidate(RecoveryActionType.WAIT, erv=0, eligible=True),
            _candidate(RecoveryActionType.CREATE_PAYMENT_LINK, erv=-10, eligible=True),
            _candidate(RecoveryActionType.STOP, erv=0, eligible=True),
        ]
    )
    selected = select_recommendation(ranked)
    assert selected is not None
    assert selected.action_type == RecoveryActionType.STOP


def test_select_stop_when_all_interventions_blocked() -> None:
    ranked = rank_candidates(
        [
            _candidate(RecoveryActionType.CREATE_PAYMENT_LINK, erv=500, eligible=False),
            _candidate(RecoveryActionType.STOP, erv=0, eligible=True),
        ]
    )
    selected = select_recommendation(ranked)
    assert selected is not None
    assert selected.action_type == RecoveryActionType.STOP


def test_positive_erv_eligible_action_prevents_stop() -> None:
    ranked = rank_candidates(
        [
            _candidate(RecoveryActionType.WAIT, erv=25, eligible=True),
            _candidate(RecoveryActionType.STOP, erv=0, eligible=True),
        ]
    )
    selected = select_recommendation(ranked)
    assert selected is not None
    assert selected.action_type == RecoveryActionType.WAIT


def test_ranking_is_deterministic() -> None:
    candidates = [
        _candidate(RecoveryActionType.WAIT, erv=100),
        _candidate(RecoveryActionType.CREATE_PAYMENT_LINK, erv=200),
        _candidate(RecoveryActionType.STOP, erv=0),
    ]
    first = rank_candidates(list(candidates))
    second = rank_candidates(list(candidates))
    assert [item.action_type for item in first] == [item.action_type for item in second]
