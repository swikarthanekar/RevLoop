"""Compute and format demo seed summaries."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.demo.constants import (
    DEMO_CASE_HIGH_VALUE_APPROVAL_ID,
    DEMO_CASE_RECOVERED_HISTORY_ID,
    DEMO_CASE_UPI_DOWNTIME_ID,
    DEMO_ORGANIZATION_ID,
    DEMO_SEED_VERSION,
)
from app.demo.factory import DemoSeedSpec, build_demo_seed_spec
from app.domain.enums import RecoveryCaseStatus
from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.models.organization import Organization
from app.models.recovery_action import RecoveryAction
from app.models.recovery_case import RecoveryCase
from app.models.recovery_outcome import RecoveryOutcome
from app.models.recovery_recommendation import RecoveryRecommendation
from app.models.subscription import Subscription
from app.models.transaction import Transaction


@dataclass(frozen=True)
class DemoSeedSummary:
    seed_version: str
    organization_name: str
    organization_id: str
    customers: int
    transactions: int
    subscriptions: int
    recovery_cases: int
    recommendations: int
    actions: int
    outcomes: int
    audit_logs: int
    active_cases: int
    recovered_cases: int
    failed_cases: int
    stopped_cases: int
    open_revenue_at_risk_minor: int
    historical_recovered_revenue_minor: int
    named_case_ids: dict[str, str]


def summary_from_spec(spec: DemoSeedSpec) -> DemoSeedSummary:
    terminal = {
        RecoveryCaseStatus.RECOVERED.value,
        RecoveryCaseStatus.FAILED.value,
        RecoveryCaseStatus.STOPPED.value,
    }
    active_cases = sum(1 for case in spec.recovery_cases if case.status not in terminal)
    recovered_cases = sum(
        1 for case in spec.recovery_cases if case.status == RecoveryCaseStatus.RECOVERED.value
    )
    failed_cases = sum(
        1 for case in spec.recovery_cases if case.status == RecoveryCaseStatus.FAILED.value
    )
    stopped_cases = sum(
        1 for case in spec.recovery_cases if case.status == RecoveryCaseStatus.STOPPED.value
    )
    open_revenue = sum(
        case.amount_at_risk_minor
        for case in spec.recovery_cases
        if case.status not in terminal
    )
    recovered_revenue = sum(outcome.recovered_amount_minor for outcome in spec.outcomes)

    return DemoSeedSummary(
        seed_version=DEMO_SEED_VERSION,
        organization_name=spec.organization.name,
        organization_id=str(spec.organization.id),
        customers=len(spec.customers),
        transactions=len(spec.transactions),
        subscriptions=len(spec.subscriptions),
        recovery_cases=len(spec.recovery_cases),
        recommendations=len(spec.recommendations),
        actions=len(spec.actions),
        outcomes=len(spec.outcomes),
        audit_logs=len(spec.audit_logs),
        active_cases=active_cases,
        recovered_cases=recovered_cases,
        failed_cases=failed_cases,
        stopped_cases=stopped_cases,
        open_revenue_at_risk_minor=open_revenue,
        historical_recovered_revenue_minor=recovered_revenue,
        named_case_ids={
            "UPI downtime": str(DEMO_CASE_UPI_DOWNTIME_ID),
            "High-value approval": str(DEMO_CASE_HIGH_VALUE_APPROVAL_ID),
            "Recovered history": str(DEMO_CASE_RECOVERED_HISTORY_ID),
        },
    )


def summary_from_database(session: Session) -> DemoSeedSummary:
    org = session.execute(
        select(Organization).where(Organization.id == DEMO_ORGANIZATION_ID)
    ).scalar_one()

    def count(model: type) -> int:
        return session.execute(
            select(func.count())
            .select_from(model)
            .where(model.organization_id == DEMO_ORGANIZATION_ID)
        ).scalar_one()

    cases = session.execute(
        select(RecoveryCase).where(RecoveryCase.organization_id == DEMO_ORGANIZATION_ID)
    ).scalars().all()

    terminal = {
        RecoveryCaseStatus.RECOVERED.value,
        RecoveryCaseStatus.FAILED.value,
        RecoveryCaseStatus.STOPPED.value,
    }
    active_cases = sum(1 for case in cases if case.status not in terminal)
    recovered_cases = sum(
        1 for case in cases if case.status == RecoveryCaseStatus.RECOVERED.value
    )
    failed_cases = sum(1 for case in cases if case.status == RecoveryCaseStatus.FAILED.value)
    stopped_cases = sum(1 for case in cases if case.status == RecoveryCaseStatus.STOPPED.value)
    open_revenue = sum(case.amount_at_risk_minor for case in cases if case.status not in terminal)
    recovered_revenue = session.execute(
        select(func.coalesce(func.sum(RecoveryOutcome.recovered_amount_minor), 0)).where(
            RecoveryOutcome.organization_id == DEMO_ORGANIZATION_ID
        )
    ).scalar_one()

    return DemoSeedSummary(
        seed_version=DEMO_SEED_VERSION,
        organization_name=org.name,
        organization_id=str(org.id),
        customers=count(Customer),
        transactions=count(Transaction),
        subscriptions=count(Subscription),
        recovery_cases=count(RecoveryCase),
        recommendations=count(RecoveryRecommendation),
        actions=count(RecoveryAction),
        outcomes=count(RecoveryOutcome),
        audit_logs=count(AuditLog),
        active_cases=active_cases,
        recovered_cases=recovered_cases,
        failed_cases=failed_cases,
        stopped_cases=stopped_cases,
        open_revenue_at_risk_minor=int(open_revenue),
        historical_recovered_revenue_minor=int(recovered_revenue),
        named_case_ids={
            "UPI downtime": str(DEMO_CASE_UPI_DOWNTIME_ID),
            "High-value approval": str(DEMO_CASE_HIGH_VALUE_APPROVAL_ID),
            "Recovered history": str(DEMO_CASE_RECOVERED_HISTORY_ID),
        },
    )


def format_inr(minor: int) -> str:
    major = Decimal(minor) / Decimal(100)
    return f"₹{major:,.2f}"


def format_summary_text(summary: DemoSeedSummary) -> str:
    lines = [
        "RevLoop demo seed complete",
        "",
        f"Seed version: {summary.seed_version}",
        f"Organization: {summary.organization_name}",
        f"Organization ID: {summary.organization_id}",
        "",
        f"Customers: {summary.customers}",
        f"Transactions: {summary.transactions}",
        f"Subscriptions: {summary.subscriptions}",
        f"Recovery cases: {summary.recovery_cases}",
        f"Recommendations: {summary.recommendations}",
        f"Actions: {summary.actions}",
        f"Outcomes: {summary.outcomes}",
        f"Audit logs: {summary.audit_logs}",
        "",
        f"Active cases: {summary.active_cases}",
        f"Recovered cases: {summary.recovered_cases}",
        f"Failed cases: {summary.failed_cases}",
        f"Stopped cases: {summary.stopped_cases}",
        "",
        f"Open revenue at risk: {format_inr(summary.open_revenue_at_risk_minor)}",
        f"Historical recovered revenue: {format_inr(summary.historical_recovered_revenue_minor)}",
        "",
        "Named demo cases:",
    ]
    for label, case_id in summary.named_case_ids.items():
        lines.append(f"{label}: {case_id}")
    return "\n".join(lines)


def build_spec_summary() -> DemoSeedSummary:
    return summary_from_spec(build_demo_seed_spec())
