"""Recovery case read services."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, NotFoundError
from app.domain.enums import PAYMENT_LINK_MECHANISM_ACTIONS, CaseType, RecoveryActionType
from app.models.recovery_action import RecoveryAction
from app.models.recovery_recommendation import RecoveryRecommendation
from app.repositories.recovery_case_repo import (
    RecoveryCaseListFilters,
    RecoveryCaseListRow,
    RecoveryCaseRepository,
)
from app.schemas.common import RecoveryCaseSort
from app.schemas.recovery_actions import CustomerActionResponse
from app.schemas.recovery_case import (
    CaseAnalysis,
    CaseCore,
    CaseOutcome,
    CustomerDetail,
    CustomerSummary,
    FailureEvidence,
    LatestAction,
    RecommendationCandidate,
    RecommendationFactor,
    RecoveryCaseDetailResponse,
    RecoveryCaseListItem,
    RecoveryCaseListResponse,
    SourceSubscription,
    SourceTransaction,
    StructuredExplanation,
)


def _decimal_to_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _build_structured_explanation(
    recommendation: RecoveryRecommendation,
) -> StructuredExplanation:
    factors = recommendation.factors or []
    factor_codes = [str(item.get("code", "")) for item in factors if item.get("code")]
    summary = (
        f"{recommendation.action_type.replace('_', ' ').title()} is preferred "
        "based on the current recovery evidence."
    )
    evidence = factor_codes or ["Demo analysis completed from seeded provider evidence."]
    safety: list[str] = []
    if not recommendation.requires_approval:
        safety.append("Amount is below automatic-action limit")
    if recommendation.policy_reasons:
        safety.extend(str(reason) for reason in recommendation.policy_reasons)
    return StructuredExplanation(summary=summary, evidence=evidence, safety=safety)


def _map_recommendation(rec: RecoveryRecommendation) -> RecommendationCandidate:
    factors = [
        RecommendationFactor(
            code=str(item.get("code", "")),
            impact=str(item.get("impact", "")),
            source=str(item.get("source", "")),
        )
        for item in (rec.factors or [])
        if item.get("code")
    ]
    policy_reasons = [str(reason) for reason in (rec.policy_reasons or [])]
    return RecommendationCandidate(
        action_type=rec.action_type,
        rank=rec.rank,
        success_probability=float(rec.success_probability),
        expected_recovered_minor=int(rec.expected_recovered_minor),
        expected_value_minor=int(rec.expected_value_minor),
        policy_eligible=rec.policy_eligible,
        requires_approval=rec.requires_approval,
        policy_reasons=policy_reasons,
        factors=factors,
    )


class RecoveryCaseService:
    def __init__(self, session: Session) -> None:
        self._repo = RecoveryCaseRepository(session)

    def list_cases(
        self,
        organization_id: UUID,
        *,
        filters: RecoveryCaseListFilters,
        sort: RecoveryCaseSort,
        limit: int,
        offset: int,
    ) -> RecoveryCaseListResponse:
        rows, total = self._repo.list_cases(
            organization_id,
            filters=filters,
            sort=sort,
            limit=limit,
            offset=offset,
        )
        return RecoveryCaseListResponse(
            items=[self._map_list_item(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    def get_case_detail(
        self,
        organization_id: UUID,
        case_id: UUID,
    ) -> RecoveryCaseDetailResponse:
        if self._repo.exists_in_other_organization(case_id, organization_id):
            raise ForbiddenError(
                code="TENANT_ACCESS_DENIED",
                message="Recovery case belongs to another organization.",
            )

        case = self._repo.get_by_id(case_id, organization_id)
        if case is None:
            raise NotFoundError(
                code="CASE_NOT_FOUND",
                message="Recovery case was not found.",
            )

        customer = self._repo.get_customer(case.customer_id, organization_id)
        if customer is None:
            raise NotFoundError(
                code="CASE_NOT_FOUND",
                message="Recovery case was not found.",
            )

        source = self._build_source(case, organization_id)
        analysis = self._build_analysis(case, organization_id)
        latest_action = self._build_latest_action(case.id, organization_id)
        outcome = self._build_outcome(case.id, organization_id)

        return RecoveryCaseDetailResponse(
            case=CaseCore(
                id=case.id,
                case_type=case.case_type,
                status=case.status,
                amount_at_risk_minor=int(case.amount_at_risk_minor),
                currency=case.currency.strip(),
                failure_category=case.failure_category,
                opened_at=case.opened_at,
                last_transition_at=case.last_transition_at,
                version=case.version,
            ),
            customer=CustomerDetail(
                id=customer.id,
                display_name=customer.display_name,
                segment=customer.segment,
                lifetime_value_minor=int(customer.lifetime_value_minor),
            ),
            source=source,
            analysis=analysis,
            latest_action=latest_action,
            outcome=outcome,
        )

    def _map_list_item(self, row: RecoveryCaseListRow) -> RecoveryCaseListItem:
        case = row.case
        return RecoveryCaseListItem(
            id=case.id,
            customer=CustomerSummary(
                id=row.customer.id,
                display_name=row.customer.display_name,
                segment=row.customer.segment,
            ),
            case_type=case.case_type,
            amount_at_risk_minor=int(case.amount_at_risk_minor),
            currency=case.currency.strip(),
            failure_category=case.failure_category,
            status=case.status,
            priority_score=_decimal_to_float(case.priority_score),
            recovery_probability=_decimal_to_float(case.recovery_probability),
            expected_recoverable_minor=(
                int(case.expected_recoverable_minor)
                if case.expected_recoverable_minor is not None
                else None
            ),
            recommended_action=row.recommended_action,
            confidence=_decimal_to_float(row.confidence),
            opened_at=case.opened_at,
        )

    def _build_source(
        self,
        case,
        organization_id: UUID,
    ) -> SourceTransaction | SourceSubscription:
        if case.case_type == CaseType.PAYMENT_FAILURE.value and case.transaction_id:
            transaction = self._repo.get_transaction(case.transaction_id, organization_id)
            if transaction is None:
                raise NotFoundError(
                    code="CASE_NOT_FOUND",
                    message="Recovery case was not found.",
                )
            return SourceTransaction(
                transaction_id=transaction.id,
                provider_payment_id=transaction.provider_payment_id,
                payment_method=(
                    transaction.payment_method.lower() if transaction.payment_method else None
                ),
                provider_status=transaction.status,
                failure_evidence=FailureEvidence(
                    error_code=transaction.error_code,
                    error_reason=transaction.error_reason,
                    error_source=transaction.error_source,
                    error_step=transaction.error_step,
                ),
            )

        if case.subscription_id:
            subscription = self._repo.get_subscription(case.subscription_id, organization_id)
            if subscription is None:
                raise NotFoundError(
                    code="CASE_NOT_FOUND",
                    message="Recovery case was not found.",
                )
            metadata = subscription.metadata_ or {}
            failure_evidence = {
                key: metadata[key]
                for key in (
                    "failure_reason",
                    "failure_category",
                    "retry_count",
                    "last_charge_status",
                )
                if key in metadata
            }
            return SourceSubscription(
                subscription_id=subscription.id,
                provider_subscription_id=subscription.provider_subscription_id,
                provider_status=subscription.status,
                failure_evidence=failure_evidence,
            )

        raise NotFoundError(
            code="CASE_NOT_FOUND",
            message="Recovery case was not found.",
        )

    def _build_analysis(self, case, organization_id: UUID) -> CaseAnalysis | None:
        if case.current_analysis_run_id is None:
            return None

        recommendations = self._repo.get_recommendations_for_analysis(
            case.id,
            organization_id,
            case.current_analysis_run_id,
        )
        if not recommendations:
            return None

        rank1 = next((rec for rec in recommendations if rec.rank == 1), recommendations[0])
        return CaseAnalysis(
            analysis_run_id=case.current_analysis_run_id,
            model_version=rank1.model_version,
            feature_schema_version=rank1.feature_schema_version,
            selected_action=rank1.action_type,
            confidence=float(rank1.confidence),
            candidates=[_map_recommendation(rec) for rec in recommendations],
            structured_explanation=_build_structured_explanation(rank1),
        )

    def _build_latest_action(self, case_id: UUID, organization_id: UUID) -> LatestAction | None:
        action = self._repo.get_latest_action(case_id, organization_id)
        if action is None:
            return None
        return LatestAction(
            id=action.id,
            action_type=action.action_type,
            status=action.status,
            attempt_number=action.attempt_number,
            requires_approval=action.requires_approval,
            scheduled_for=action.scheduled_for,
            executed_at=action.executed_at,
            provider_reference=action.provider_reference,
            provider_status=action.provider_status,
            customer_action=self._build_customer_action(action),
        )

    def _build_customer_action(self, action: RecoveryAction) -> CustomerActionResponse | None:
        if RecoveryActionType(action.action_type) not in PAYMENT_LINK_MECHANISM_ACTIONS:
            return None
        short_url = action.metadata_.get("short_url")
        if not short_url:
            return None
        return CustomerActionResponse(type="PAYMENT_LINK", url=str(short_url))

    def _build_outcome(self, case_id: UUID, organization_id: UUID) -> CaseOutcome | None:
        outcome = self._repo.get_outcome(case_id, organization_id)
        if outcome is None:
            return None
        return CaseOutcome(
            outcome=outcome.outcome,
            recovered_amount_minor=int(outcome.recovered_amount_minor),
            recovered_payment_id=outcome.recovered_payment_id,
            verification_source=outcome.verification_source,
            recovered_at=outcome.recovered_at,
            time_to_recovery_seconds=(
                int(outcome.time_to_recovery_seconds)
                if outcome.time_to_recovery_seconds is not None
                else None
            ),
        )
