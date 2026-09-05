"""One definition of "which candidate did the engine choose?".

The selection rule is needed in four places that hold the candidates in four
different shapes:

- the analysis write path, on `RankedRecommendationCandidate` (pydantic);
- the case-detail read path, on `RecoveryRecommendation` (ORM rows);
- demo seeding, on `RecommendationSpec` (frozen dataclasses);
- tests.

Reimplementing the rule per shape is how the write and read paths came to
disagree in the first place: analysis selected one action while case detail
reported rank 1 as "selected", and the UI rendered a button for the latter.
This module adapts any of those shapes onto the single implementation in
`app.recovery.ranking.select_recommendation`, so there is exactly one rule.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol, TypeVar

from app.domain.capabilities import advisory_reason_code, execution_mode
from app.domain.enums import RecoveryActionType
from app.recovery.ranking import OPERATIONAL_BURDEN, select_recommendation
from app.recovery.schemas import RankedRecommendationCandidate


class CandidateRow(Protocol):
    """The fields every persisted or specified candidate shape already has."""

    action_type: str
    rank: int
    success_probability: object
    expected_recovered_minor: int
    expected_value_minor: int
    confidence: object
    policy_eligible: bool
    requires_approval: bool


RowT = TypeVar("RowT", bound=CandidateRow)


def _to_ranked(row: CandidateRow) -> RankedRecommendationCandidate:
    action = RecoveryActionType(row.action_type)
    return RankedRecommendationCandidate(
        action_type=action,
        success_probability=Decimal(str(row.success_probability)),
        expected_recovered_minor=int(row.expected_recovered_minor),
        expected_value_minor=int(row.expected_value_minor),
        confidence=Decimal(str(row.confidence)),
        eligible=bool(row.policy_eligible),
        requires_approval=bool(row.requires_approval),
        policy_reasons=tuple(
            str(reason) for reason in (getattr(row, "policy_reasons", None) or [])
        ),
        operational_burden=OPERATIONAL_BURDEN[action],
        execution_mode=execution_mode(action),
        advisory_reason_code=advisory_reason_code(action),
        rank=int(row.rank),
    )


def select_candidate_row(rows: list[RowT]) -> RowT | None:
    """The row the Execute control should target, or None if there is none.

    Applies `select_recommendation` -- highest-ranked candidate that is policy
    eligible, executable by RevLoop, non-STOP and positive expected value, with
    an eligible STOP as the terminal fallback.
    """
    if not rows:
        return None
    ordered = sorted(rows, key=lambda row: int(row.rank))
    by_action = {row.action_type: row for row in ordered}
    selected = select_recommendation([_to_ranked(row) for row in ordered])
    if selected is None:
        return None
    return by_action.get(selected.action_type.value)


def top_ranked_row(rows: list[RowT]) -> RowT | None:
    """The model's own first choice, advisory or not."""
    if not rows:
        return None
    return min(rows, key=lambda row: int(row.rank))


__all__ = ["CandidateRow", "select_candidate_row", "top_ranked_row"]
