"""Data access helpers for dashboard analytics aggregates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, and_, case, cast, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.types import Date

from app.domain.enums import RecoveryCaseStatus, RecoveryOutcomeType
from app.models.recovery_action import RecoveryAction
from app.models.recovery_case import RecoveryCase
from app.models.recovery_outcome import RecoveryOutcome
from app.models.recovery_recommendation import RecoveryRecommendation
from app.models.subscription import Subscription
from app.models.transaction import Transaction
from app.schemas.common import DashboardSourceFilter

TERMINAL_STATUSES = (
    RecoveryCaseStatus.RECOVERED.value,
    RecoveryCaseStatus.FAILED.value,
    RecoveryCaseStatus.STOPPED.value,
)

NAIVE_BASELINE_ACTIONS = ("RETRY_SAME_METHOD", "WAIT")
NAIVE_BASELINE_RECOVERY_RATE = Decimal("0.40")


@dataclass(frozen=True)
class DashboardAggregateRow:
    revenue_at_risk_minor: int
    revenue_recovered_minor: int
    baseline_recovered_minor: int
    active_cases: int
    recovered_cases: int
    average_recovery_seconds: int | None
    synthetic_case_count: int
    total_case_count: int


@dataclass(frozen=True)
class TrendRow:
    date: str
    at_risk_minor: int
    recovered_minor: int


@dataclass(frozen=True)
class ActionEffectivenessRow:
    action_type: str
    attempted: int
    recovered: int
    recovered_minor: int


@dataclass(frozen=True)
class FailureBreakdownRow:
    failure_category: str
    cases: int
    amount_minor: int


def _source_clause(source: DashboardSourceFilter) -> list:
    if source == DashboardSourceFilter.ALL:
        return []
    if source == DashboardSourceFilter.SYNTHETIC:
        return [
            or_(
                and_(RecoveryCase.transaction_id.is_not(None), Transaction.is_synthetic.is_(True)),
                and_(
                    RecoveryCase.subscription_id.is_not(None),
                    Subscription.is_synthetic.is_(True),
                ),
            )
        ]
    return [
        or_(
            and_(RecoveryCase.transaction_id.is_not(None), Transaction.is_synthetic.is_(False)),
            and_(
                RecoveryCase.subscription_id.is_not(None),
                Subscription.is_synthetic.is_(False),
            ),
        )
    ]


def _scoped_cases_query(
    organization_id: UUID,
    *,
    from_dt: datetime | None,
    to_dt: datetime | None,
    source: DashboardSourceFilter,
) -> Select[tuple[RecoveryCase]]:
    stmt = (
        select(RecoveryCase)
        .outerjoin(Transaction, RecoveryCase.transaction_id == Transaction.id)
        .outerjoin(Subscription, RecoveryCase.subscription_id == Subscription.id)
        .where(RecoveryCase.organization_id == organization_id)
    )
    if from_dt is not None:
        stmt = stmt.where(RecoveryCase.opened_at >= from_dt)
    if to_dt is not None:
        stmt = stmt.where(RecoveryCase.opened_at <= to_dt)
    for clause in _source_clause(source):
        stmt = stmt.where(clause)
    return stmt


def _case_ids_subquery(
    organization_id: UUID,
    *,
    from_dt: datetime | None,
    to_dt: datetime | None,
    source: DashboardSourceFilter,
) -> Select[tuple[UUID]]:
    return _scoped_cases_query(
        organization_id,
        from_dt=from_dt,
        to_dt=to_dt,
        source=source,
    ).with_only_columns(RecoveryCase.id)


class AnalyticsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_dashboard_aggregates(
        self,
        organization_id: UUID,
        *,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        source: DashboardSourceFilter = DashboardSourceFilter.ALL,
    ) -> DashboardAggregateRow:
        case_ids = _case_ids_subquery(
            organization_id,
            from_dt=from_dt,
            to_dt=to_dt,
            source=source,
        ).subquery()

        active_statuses = [
            status.value
            for status in RecoveryCaseStatus
            if status.value not in TERMINAL_STATUSES
        ]

        revenue_at_risk = self._session.execute(
            select(func.coalesce(func.sum(RecoveryCase.amount_at_risk_minor), 0)).where(
                RecoveryCase.organization_id == organization_id,
                RecoveryCase.id.in_(select(case_ids.c.id)),
                RecoveryCase.status.in_(active_statuses),
            )
        ).scalar_one()

        revenue_recovered = self._session.execute(
            select(func.coalesce(func.sum(RecoveryOutcome.recovered_amount_minor), 0))
            .select_from(RecoveryOutcome)
            .join(RecoveryCase, RecoveryOutcome.case_id == RecoveryCase.id)
            .where(
                RecoveryOutcome.organization_id == organization_id,
                RecoveryOutcome.outcome == RecoveryOutcomeType.RECOVERED.value,
                RecoveryCase.id.in_(select(case_ids.c.id)),
            )
        ).scalar_one()

        active_cases = self._session.execute(
            select(func.count())
            .select_from(RecoveryCase)
            .where(
                RecoveryCase.organization_id == organization_id,
                RecoveryCase.id.in_(select(case_ids.c.id)),
                RecoveryCase.status.in_(active_statuses),
            )
        ).scalar_one()

        recovered_cases = self._session.execute(
            select(func.count())
            .select_from(RecoveryCase)
            .where(
                RecoveryCase.organization_id == organization_id,
                RecoveryCase.id.in_(select(case_ids.c.id)),
                RecoveryCase.status == RecoveryCaseStatus.RECOVERED.value,
            )
        ).scalar_one()

        avg_recovery_seconds = self._session.execute(
            select(func.avg(RecoveryOutcome.time_to_recovery_seconds))
            .select_from(RecoveryOutcome)
            .join(RecoveryCase, RecoveryOutcome.case_id == RecoveryCase.id)
            .where(
                RecoveryOutcome.organization_id == organization_id,
                RecoveryOutcome.time_to_recovery_seconds.is_not(None),
                RecoveryCase.id.in_(select(case_ids.c.id)),
            )
        ).scalar_one()

        baseline_recovered = self._compute_baseline_recovered(
            organization_id,
            case_ids=case_ids,
        )

        synthetic_count, total_count = self._session.execute(
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (
                                or_(
                                    Transaction.is_synthetic.is_(True),
                                    Subscription.is_synthetic.is_(True),
                                ),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.count(),
            )
            .select_from(RecoveryCase)
            .outerjoin(Transaction, RecoveryCase.transaction_id == Transaction.id)
            .outerjoin(Subscription, RecoveryCase.subscription_id == Subscription.id)
            .where(
                RecoveryCase.organization_id == organization_id,
                RecoveryCase.id.in_(select(case_ids.c.id)),
            )
        ).one()

        avg_seconds_int = int(avg_recovery_seconds) if avg_recovery_seconds is not None else None

        return DashboardAggregateRow(
            revenue_at_risk_minor=int(revenue_at_risk),
            revenue_recovered_minor=int(revenue_recovered),
            baseline_recovered_minor=int(baseline_recovered),
            active_cases=int(active_cases),
            recovered_cases=int(recovered_cases),
            average_recovery_seconds=avg_seconds_int,
            synthetic_case_count=int(synthetic_count),
            total_case_count=int(total_count),
        )

    def _compute_baseline_recovered(
        self,
        organization_id: UUID,
        *,
        case_ids,
    ) -> int:
        """Estimate naive immediate-retry recovery from rank-1 recommendations."""
        rank1 = (
            select(
                RecoveryRecommendation.case_id,
                RecoveryRecommendation.action_type,
                RecoveryRecommendation.expected_recovered_minor,
            )
            .where(
                RecoveryRecommendation.organization_id == organization_id,
                RecoveryRecommendation.rank == 1,
                RecoveryRecommendation.case_id.in_(select(case_ids.c.id)),
            )
            .subquery()
        )

        rows = self._session.execute(
            select(
                RecoveryOutcome.recovered_amount_minor,
                rank1.c.action_type,
                rank1.c.expected_recovered_minor,
                RecoveryCase.amount_at_risk_minor,
            )
            .select_from(RecoveryOutcome)
            .join(RecoveryCase, RecoveryOutcome.case_id == RecoveryCase.id)
            .outerjoin(rank1, rank1.c.case_id == RecoveryCase.id)
            .where(
                RecoveryOutcome.organization_id == organization_id,
                RecoveryOutcome.outcome == RecoveryOutcomeType.RECOVERED.value,
                RecoveryCase.id.in_(select(case_ids.c.id)),
            )
        ).all()

        total = 0
        for recovered_amount, action_type, expected_recovered, amount_at_risk in rows:
            if action_type in NAIVE_BASELINE_ACTIONS and expected_recovered is not None:
                total += min(int(recovered_amount), int(expected_recovered))
            else:
                total += int(
                    (Decimal(amount_at_risk) * NAIVE_BASELINE_RECOVERY_RATE).to_integral_value()
                )
        return total

    def get_recovery_trend(
        self,
        organization_id: UUID,
        *,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        source: DashboardSourceFilter = DashboardSourceFilter.ALL,
    ) -> list[TrendRow]:
        case_ids = _case_ids_subquery(
            organization_id,
            from_dt=from_dt,
            to_dt=to_dt,
            source=source,
        ).subquery()

        at_risk_rows = self._session.execute(
            select(
                cast(func.date_trunc("day", RecoveryCase.opened_at), Date).label("day"),
                func.coalesce(func.sum(RecoveryCase.amount_at_risk_minor), 0),
            )
            .where(
                RecoveryCase.organization_id == organization_id,
                RecoveryCase.id.in_(select(case_ids.c.id)),
            )
            .group_by("day")
            .order_by("day")
        ).all()

        recovered_rows = self._session.execute(
            select(
                cast(func.date_trunc("day", RecoveryOutcome.recovered_at), Date).label("day"),
                func.coalesce(func.sum(RecoveryOutcome.recovered_amount_minor), 0),
            )
            .select_from(RecoveryOutcome)
            .join(RecoveryCase, RecoveryOutcome.case_id == RecoveryCase.id)
            .where(
                RecoveryOutcome.organization_id == organization_id,
                RecoveryOutcome.outcome == RecoveryOutcomeType.RECOVERED.value,
                RecoveryOutcome.recovered_at.is_not(None),
                RecoveryCase.id.in_(select(case_ids.c.id)),
            )
            .group_by("day")
            .order_by("day")
        ).all()

        at_risk_by_day = {row[0].isoformat(): int(row[1]) for row in at_risk_rows if row[0]}
        recovered_by_day = {row[0].isoformat(): int(row[1]) for row in recovered_rows if row[0]}
        all_days = sorted(set(at_risk_by_day) | set(recovered_by_day))

        return [
            TrendRow(
                date=day,
                at_risk_minor=at_risk_by_day.get(day, 0),
                recovered_minor=recovered_by_day.get(day, 0),
            )
            for day in all_days
        ]

    def get_action_effectiveness(
        self,
        organization_id: UUID,
        *,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        source: DashboardSourceFilter = DashboardSourceFilter.ALL,
    ) -> list[ActionEffectivenessRow]:
        case_ids = _case_ids_subquery(
            organization_id,
            from_dt=from_dt,
            to_dt=to_dt,
            source=source,
        ).subquery()

        recovered_case_ids = (
            select(RecoveryCase.id)
            .where(
                RecoveryCase.organization_id == organization_id,
                RecoveryCase.status == RecoveryCaseStatus.RECOVERED.value,
                RecoveryCase.id.in_(select(case_ids.c.id)),
            )
            .subquery()
        )

        rows = self._session.execute(
            select(
                RecoveryAction.action_type,
                func.count().label("attempted"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                RecoveryAction.case_id.in_(select(recovered_case_ids.c.id)),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("recovered"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                and_(
                                    RecoveryAction.case_id.in_(select(recovered_case_ids.c.id)),
                                    RecoveryOutcome.recovered_amount_minor.is_not(None),
                                ),
                                RecoveryOutcome.recovered_amount_minor,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("recovered_minor"),
            )
            .select_from(RecoveryAction)
            .outerjoin(
                RecoveryOutcome,
                and_(
                    RecoveryOutcome.case_id == RecoveryAction.case_id,
                    RecoveryOutcome.organization_id == RecoveryAction.organization_id,
                ),
            )
            .where(
                RecoveryAction.organization_id == organization_id,
                RecoveryAction.case_id.in_(select(case_ids.c.id)),
            )
            .group_by(RecoveryAction.action_type)
            .order_by(RecoveryAction.action_type)
        ).all()

        return [
            ActionEffectivenessRow(
                action_type=row.action_type,
                attempted=int(row.attempted),
                recovered=int(row.recovered),
                recovered_minor=int(row.recovered_minor),
            )
            for row in rows
        ]

    def get_failure_breakdown(
        self,
        organization_id: UUID,
        *,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        source: DashboardSourceFilter = DashboardSourceFilter.ALL,
    ) -> list[FailureBreakdownRow]:
        case_ids = _case_ids_subquery(
            organization_id,
            from_dt=from_dt,
            to_dt=to_dt,
            source=source,
        ).subquery()

        rows = self._session.execute(
            select(
                func.coalesce(RecoveryCase.failure_category, "UNKNOWN").label("failure_category"),
                func.count().label("cases"),
                func.coalesce(func.sum(RecoveryCase.amount_at_risk_minor), 0).label("amount_minor"),
            )
            .where(
                RecoveryCase.organization_id == organization_id,
                RecoveryCase.id.in_(select(case_ids.c.id)),
            )
            .group_by("failure_category")
            .order_by(func.sum(RecoveryCase.amount_at_risk_minor).desc())
        ).all()

        return [
            FailureBreakdownRow(
                failure_category=row.failure_category,
                cases=int(row.cases),
                amount_minor=int(row.amount_minor),
            )
            for row in rows
        ]
