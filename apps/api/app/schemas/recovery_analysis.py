"""Request/response schemas for recovery analysis API."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import AnalysisReason, RecoveryCaseStatus


class AnalyzeRecoveryCaseRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    reason: AnalysisReason = AnalysisReason.MANUAL_ANALYSIS


class SelectedRecommendationResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    action_type: str
    success_probability: float = Field(ge=0.0, le=1.0)
    expected_recovered_minor: int = Field(ge=0)
    expected_value_minor: int
    confidence: float = Field(ge=0.0, le=1.0)
    requires_approval: bool


class CandidateRecommendationResponse(SelectedRecommendationResponse):
    model_config = ConfigDict(frozen=True)

    rank: int = Field(ge=1)
    policy_eligible: bool


class RecommendationExplanationResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    summary: str
    evidence: list[str]
    safety: list[str]
    customer_impact: str | None = None


class AnalyzeRecoveryCaseResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_id: UUID
    analysis_run_id: UUID
    status: RecoveryCaseStatus
    selected: SelectedRecommendationResponse | None
    candidates: list[CandidateRecommendationResponse]
    explanation: RecommendationExplanationResponse | None = None
    explanation_source: str | None = None
