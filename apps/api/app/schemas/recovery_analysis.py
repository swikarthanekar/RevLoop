"""Request/response schemas for recovery analysis API."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.capabilities import ActionExecutionMode
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
    #: EXECUTABLE or ADVISORY, from `app.domain.capabilities`. `policy_eligible`
    #: answers "does merchant policy permit this?"; this answers the separate
    #: question "can RevLoop carry it out at all?". Both are needed: an action
    #: can be policy-eligible and still not something RevLoop performs.
    execution_mode: ActionExecutionMode
    advisory_reason_code: str | None = None
    advisory_reason: str | None = None


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
    #: The chosen action, always one RevLoop can execute. None when no eligible
    #: executable candidate exists.
    selected: SelectedRecommendationResponse | None
    #: The model's top-ranked action, which may be ADVISORY and so may differ
    #: from `selected`. Stated explicitly so a client never has to reimplement
    #: the selection rule to explain the difference to an operator.
    top_ranked_action: str | None = None
    candidates: list[CandidateRecommendationResponse]
    explanation: RecommendationExplanationResponse | None = None
    explanation_source: str | None = None
