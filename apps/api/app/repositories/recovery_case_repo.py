"""Repository for tenant-scoped recovery case reads."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, and_, desc, func, or_, select, tuple_
from sqlalchemy.orm import Session, aliased

from app.models.customer import Customer
from app.models.recovery_action import RecoveryAction
from app.models.recovery_case import RecoveryCase
from app.models.recovery_outcome import RecoveryOutcome
from app.models.recovery_recommendation import RecoveryRecommendation
from app.models.subscription import Subscription
from app.models.transaction import Transaction
from app.recovery.selection import select_candidate_row
from app.schemas.common import RecoveryCaseSort


@dataclass(frozen=True)
class RecoveryCaseListFilters:
    statuses: list[str] | None = None
    case_type: str | None = None
    failure_category: str | None = None
    min_amount_minor: int | None = None
    max_amount_minor: int | None = None
    min_confidence: float | None = None
    customer_id: UUID | None = None
    search: str | None = None


@dataclass(frozen=True)
class RecoveryCaseListRow:
    case: RecoveryCase
    customer: Customer
    recommended_action: str | None
    confidence: Decimal | None


class RecoveryCaseRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def exists_for_organization(self, case_id: UUID, organization_id: UUID) -> bool:
        result = self._session.execute(
            select(RecoveryCase.id).where(
                RecoveryCase.id == case_id,
                RecoveryCase.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        return result is not None

    def exists_in_other_organization(self, case_id: UUID, organization_id: UUID) -> bool:
        result = self._session.execute(
            select(RecoveryCase.id).where(
                RecoveryCase.id == case_id,
                RecoveryCase.organization_id != organization_id,
            )
        ).scalar_one_or_none()
        return result is not None

    def get_by_id(self, case_id: UUID, organization_id: UUID) -> RecoveryCase | None:
        return self._session.execute(
            select(RecoveryCase).where(
                RecoveryCase.id == case_id,
                RecoveryCase.organization_id == organization_id,
            )
        ).scalar_one_or_none()

    def get_customer(self, customer_id: UUID, organization_id: UUID) -> Customer | None:
        return self._session.execute(
            select(Customer).where(
                Customer.id == customer_id,
                Customer.organization_id == organization_id,
            )
        ).scalar_one_or_none()

    def get_transaction(self, transaction_id: UUID, organization_id: UUID) -> Transaction | None:
        return self._session.execute(
            select(Transaction).where(
                Transaction.id == transaction_id,
                Transaction.organization_id == organization_id,
            )
        ).scalar_one_or_none()

    def get_subscription(self, subscription_id: UUID, organization_id: UUID) -> Subscription | None:
        return self._session.execute(
            select(Subscription).where(
                Subscription.id == subscription_id,
                Subscription.organization_id == organization_id,
            )
        ).scalar_one_or_none()

    def get_recommendations_for_analysis(
        self,
        case_id: UUID,
        organization_id: UUID,
        analysis_run_id: UUID,
    ) -> list[RecoveryRecommendation]:
        return list(
            self._session.execute(
                select(RecoveryRecommendation)
                .where(
                    RecoveryRecommendation.case_id == case_id,
                    RecoveryRecommendation.organization_id == organization_id,
                    RecoveryRecommendation.analysis_run_id == analysis_run_id,
                )
                .order_by(RecoveryRecommendation.rank)
            ).scalars()
        )

    def get_latest_action(self, case_id: UUID, organization_id: UUID) -> RecoveryAction | None:
        return self._session.execute(
            select(RecoveryAction)
            .where(
                RecoveryAction.case_id == case_id,
                RecoveryAction.organization_id == organization_id,
            )
            .order_by(desc(RecoveryAction.attempt_number), desc(RecoveryAction.created_at))
            .limit(1)
        ).scalar_one_or_none()

    def get_outcome(self, case_id: UUID, organization_id: UUID) -> RecoveryOutcome | None:
        return self._session.execute(
            select(RecoveryOutcome).where(
                RecoveryOutcome.case_id == case_id,
                RecoveryOutcome.organization_id == organization_id,
            )
        ).scalar_one_or_none()

    def list_cases(
        self,
        organization_id: UUID,
        *,
        filters: RecoveryCaseListFilters,
        sort: RecoveryCaseSort,
        limit: int,
        offset: int,
    ) -> tuple[list[RecoveryCaseListRow], int]:
        rank1 = aliased(RecoveryRecommendation)
        stmt = (
            select(RecoveryCase, Customer, rank1.action_type, rank1.confidence)
            .join(Customer, RecoveryCase.customer_id == Customer.id)
            .outerjoin(
                rank1,
                and_(
                    rank1.case_id == RecoveryCase.id,
                    rank1.organization_id == RecoveryCase.organization_id,
                    rank1.analysis_run_id == RecoveryCase.current_analysis_run_id,
                    rank1.rank == 1,
                ),
            )
            .where(
                RecoveryCase.organization_id == organization_id,
                Customer.organization_id == organization_id,
            )
        )

        stmt = self._apply_filters(stmt, filters, rank1)

        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = self._session.execute(count_stmt).scalar_one()

        stmt = self._apply_sort(stmt, sort)
        stmt = stmt.limit(limit).offset(offset)

        rows = self._session.execute(stmt).all()
        # The join above resolves rank 1, which is not necessarily the action
        # the engine selected: when rank 1 is advisory, selection picks a
        # lower-ranked executable action. Left uncorrected, the list would
        # advertise an action that the case detail then contradicts and that
        # the executor refuses.
        #
        # Applied in Python rather than in the join because selection is
        # "highest-ranked candidate that is eligible, executable, non-STOP and
        # positive value", which is not a predicate on a single row. Expressing
        # it in SQL would be a second implementation of a rule that has already
        # drifted once.
        selected_by_case = self._selected_actions_for(
            [row[0] for row in rows]
        )
        items = []
        for row in rows:
            case = row[0]
            selected = selected_by_case.get((case.id, case.current_analysis_run_id))
            items.append(
                RecoveryCaseListRow(
                    case=case,
                    customer=row[1],
                    recommended_action=(
                        selected.action_type if selected is not None else row[2]
                    ),
                    confidence=selected.confidence if selected is not None else row[3],
                )
            )
        return items, int(total)

    def _selected_actions_for(
        self,
        cases: list[RecoveryCase],
    ) -> dict[tuple[UUID, UUID], RecoveryRecommendation]:
        """The selected recommendation for each listed case, in one query.

        Keyed on (case id, analysis run id) so a recommendation from a
        superseded run can never be attributed to the current one.
        """
        keys = [
            (case.id, case.current_analysis_run_id)
            for case in cases
            if case.current_analysis_run_id is not None
        ]
        if not keys:
            return {}

        candidates = self._session.execute(
            select(RecoveryRecommendation).where(
                tuple_(
                    RecoveryRecommendation.case_id,
                    RecoveryRecommendation.analysis_run_id,
                ).in_(keys)
            )
        ).scalars()

        grouped: dict[tuple[UUID, UUID], list[RecoveryRecommendation]] = {}
        for candidate in candidates:
            grouped.setdefault(
                (candidate.case_id, candidate.analysis_run_id), []
            ).append(candidate)

        return {
            key: selected
            for key, rows in grouped.items()
            if (selected := select_candidate_row(rows)) is not None
        }

    def _apply_filters(
        self,
        stmt: Select,
        filters: RecoveryCaseListFilters,
        rank1: type[RecoveryRecommendation],
    ) -> Select:
        if filters.statuses:
            stmt = stmt.where(RecoveryCase.status.in_(filters.statuses))
        if filters.case_type is not None:
            stmt = stmt.where(RecoveryCase.case_type == filters.case_type)
        if filters.failure_category is not None:
            stmt = stmt.where(RecoveryCase.failure_category == filters.failure_category)
        if filters.min_amount_minor is not None:
            stmt = stmt.where(RecoveryCase.amount_at_risk_minor >= filters.min_amount_minor)
        if filters.max_amount_minor is not None:
            stmt = stmt.where(RecoveryCase.amount_at_risk_minor <= filters.max_amount_minor)
        if filters.min_confidence is not None:
            stmt = stmt.where(rank1.confidence >= filters.min_confidence)
        if filters.customer_id is not None:
            stmt = stmt.where(RecoveryCase.customer_id == filters.customer_id)
        if filters.search:
            pattern = f"%{filters.search.strip()}%"
            stmt = stmt.where(
                or_(
                    Customer.display_name.ilike(pattern),
                    Customer.external_id.ilike(pattern),
                )
            )
        return stmt

    def _apply_sort(self, stmt: Select, sort: RecoveryCaseSort) -> Select:
        if sort == RecoveryCaseSort.AMOUNT_DESC:
            return stmt.order_by(
                desc(RecoveryCase.amount_at_risk_minor),
                desc(RecoveryCase.id),
            )
        if sort == RecoveryCaseSort.OPENED_DESC:
            return stmt.order_by(
                desc(RecoveryCase.opened_at),
                desc(RecoveryCase.id),
            )
        return stmt.order_by(
            desc(RecoveryCase.priority_score).nulls_last(),
            desc(RecoveryCase.opened_at),
            desc(RecoveryCase.id),
        )
