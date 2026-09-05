"""Dashboard analytics composition."""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.demo.constants import DEMO_SOURCE_LABEL
from app.repositories.analytics_repo import (
    NAIVE_BASELINE_ACTIONS,
    NAIVE_BASELINE_RECOVERY_RATE,
    AnalyticsRepository,
)
from app.schemas.common import DashboardSourceFilter
from app.schemas.dashboard import (
    ActionEffectivenessRow,
    BaselineAssumption,
    DashboardSummaryResponse,
    FailureBreakdownRow,
    RecoveryTrendPoint,
)


def _baseline_assumption() -> BaselineAssumption:
    """Describe the counterfactual behind `baseline_recovered_minor`.

    Built from the same constants the calculation uses, so the disclosure and
    the number can never disagree.
    """
    rate = NAIVE_BASELINE_RECOVERY_RATE
    return BaselineAssumption(
        naive_recovery_rate=float(rate),
        naive_actions=list(NAIVE_BASELINE_ACTIONS),
        description=(
            "Modelled counterfactual, not a measured control group. Where the "
            "naive policy would have chosen the same action RevLoop did "
            f"({' or '.join(NAIVE_BASELINE_ACTIONS)}), it is credited with the "
            "same expected recovery; otherwise it is assumed to recover "
            f"{rate:.0%} of the amount at risk. No untreated holdout exists in "
            "this dataset, so this is an assumption, not an observation."
        ),
    )


def _recovery_rate(recovered_minor: int, at_risk_minor: int) -> float:
    denominator = recovered_minor + at_risk_minor
    if denominator <= 0:
        return 0.0
    rate = Decimal(recovered_minor) / Decimal(denominator)
    return float(rate.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def _action_recovery_rate(recovered: int, attempted: int) -> float:
    if attempted <= 0:
        return 0.0
    rate = Decimal(recovered) / Decimal(attempted)
    return float(rate.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def _resolve_source_label(synthetic_case_count: int, total_case_count: int) -> str:
    if total_case_count == 0:
        return DEMO_SOURCE_LABEL
    if synthetic_case_count == total_case_count:
        return DEMO_SOURCE_LABEL
    if synthetic_case_count == 0:
        return "RAZORPAY_TEST"
    return "MIXED"


class AnalyticsService:
    def __init__(self, session: Session) -> None:
        self._repo = AnalyticsRepository(session)

    def get_dashboard_summary(
        self,
        organization_id: UUID,
        *,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        source: DashboardSourceFilter = DashboardSourceFilter.ALL,
        currency: str = "INR",
    ) -> DashboardSummaryResponse:
        aggregates = self._repo.get_dashboard_aggregates(
            organization_id,
            from_dt=from_dt,
            to_dt=to_dt,
            source=source,
        )
        trend_rows = self._repo.get_recovery_trend(
            organization_id,
            from_dt=from_dt,
            to_dt=to_dt,
            source=source,
        )
        action_rows = self._repo.get_action_effectiveness(
            organization_id,
            from_dt=from_dt,
            to_dt=to_dt,
            source=source,
        )
        failure_rows = self._repo.get_failure_breakdown(
            organization_id,
            from_dt=from_dt,
            to_dt=to_dt,
            source=source,
        )

        incremental = max(
            0,
            aggregates.revenue_recovered_minor - aggregates.baseline_recovered_minor,
        )

        return DashboardSummaryResponse(
            currency=currency,
            revenue_at_risk_minor=aggregates.revenue_at_risk_minor,
            revenue_recovered_minor=aggregates.revenue_recovered_minor,
            baseline_recovered_minor=aggregates.baseline_recovered_minor,
            incremental_recovered_minor=incremental,
            baseline_assumption=_baseline_assumption(),
            recovery_rate=_recovery_rate(
                aggregates.revenue_recovered_minor,
                aggregates.revenue_at_risk_minor,
            ),
            active_cases=aggregates.active_cases,
            recovered_cases=aggregates.recovered_cases,
            average_recovery_seconds=aggregates.average_recovery_seconds,
            recovery_trend=[
                RecoveryTrendPoint(
                    date=row.date,
                    at_risk_minor=row.at_risk_minor,
                    recovered_minor=row.recovered_minor,
                )
                for row in trend_rows
            ],
            action_effectiveness=[
                ActionEffectivenessRow(
                    action_type=row.action_type,
                    attempted=row.attempted,
                    recovered=row.recovered,
                    recovery_rate=_action_recovery_rate(row.recovered, row.attempted),
                    recovered_minor=row.recovered_minor,
                )
                for row in action_rows
            ],
            failure_breakdown=[
                FailureBreakdownRow(
                    failure_category=row.failure_category,
                    cases=row.cases,
                    amount_minor=row.amount_minor,
                )
                for row in failure_rows
            ],
            source_label=_resolve_source_label(
                aggregates.synthetic_case_count,
                aggregates.total_case_count,
            ),
        )
