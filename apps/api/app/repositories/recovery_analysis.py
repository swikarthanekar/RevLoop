"""Persistence helpers for immutable recovery analysis runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.recovery_case import RecoveryCase
from app.models.recovery_recommendation import RecoveryRecommendation


@dataclass(frozen=True)
class RecommendationPersistenceRow:
    action_type: str
    rank: int
    success_probability: Decimal
    expected_recovered_minor: int
    expected_value_minor: int
    #: Components of `expected_value_minor`, stored so the arithmetic can be
    #: shown exactly rather than recomputed and possibly failing to reconcile.
    erv_action_cost_minor: int
    erv_fatigue_penalty_minor: int
    erv_operational_risk_penalty_minor: int
    erv_delay_penalty_minor: int
    confidence: Decimal
    policy_eligible: bool
    requires_approval: bool
    policy_reasons: list[str]
    factors: list[dict[str, str]]
    model_version: str
    feature_schema_version: str


@dataclass(frozen=True)
class CaseAnalysisSummaryUpdate:
    current_analysis_run_id: UUID
    priority_score: Decimal
    recovery_probability: Decimal
    expected_recoverable_minor: int


class RecoveryAnalysisRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def count_recommendations_for_run(
        self,
        *,
        case_id: UUID,
        organization_id: UUID,
        analysis_run_id: UUID,
    ) -> int:
        result = self._session.execute(
            select(RecoveryRecommendation.id).where(
                RecoveryRecommendation.case_id == case_id,
                RecoveryRecommendation.organization_id == organization_id,
                RecoveryRecommendation.analysis_run_id == analysis_run_id,
            )
        ).all()
        return len(result)

    def persist_analysis_run(
        self,
        *,
        organization_id: UUID,
        case_id: UUID,
        analysis_run_id: UUID,
        recommendations: list[RecommendationPersistenceRow],
        case_update: CaseAnalysisSummaryUpdate,
        updated_at: datetime,
    ) -> None:
        for row in recommendations:
            self._session.add(
                RecoveryRecommendation(
                    organization_id=organization_id,
                    case_id=case_id,
                    analysis_run_id=analysis_run_id,
                    action_type=row.action_type,
                    rank=row.rank,
                    success_probability=row.success_probability,
                    expected_recovered_minor=row.expected_recovered_minor,
                    expected_value_minor=row.expected_value_minor,
                    erv_action_cost_minor=row.erv_action_cost_minor,
                    erv_fatigue_penalty_minor=row.erv_fatigue_penalty_minor,
                    erv_operational_risk_penalty_minor=(
                        row.erv_operational_risk_penalty_minor
                    ),
                    erv_delay_penalty_minor=row.erv_delay_penalty_minor,
                    confidence=row.confidence,
                    policy_eligible=row.policy_eligible,
                    requires_approval=row.requires_approval,
                    policy_reasons=row.policy_reasons,
                    factors=row.factors,
                    model_version=row.model_version,
                    feature_schema_version=row.feature_schema_version,
                )
            )

        self._session.execute(
            update(RecoveryCase)
            .where(
                RecoveryCase.id == case_id,
                RecoveryCase.organization_id == organization_id,
            )
            .values(
                current_analysis_run_id=case_update.current_analysis_run_id,
                priority_score=case_update.priority_score,
                recovery_probability=case_update.recovery_probability,
                expected_recoverable_minor=case_update.expected_recoverable_minor,
                updated_at=updated_at,
            )
        )
