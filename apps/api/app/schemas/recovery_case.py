from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import PaginatedResponse
from app.schemas.recovery_actions import CustomerActionResponse


class CustomerSummary(BaseModel):
    id: UUID
    display_name: str
    segment: str


class CustomerDetail(CustomerSummary):
    lifetime_value_minor: int


class RecoveryCaseListItem(BaseModel):
    id: UUID
    customer: CustomerSummary
    case_type: str
    amount_at_risk_minor: int
    currency: str
    failure_category: str | None
    status: str
    priority_score: float | None
    recovery_probability: float | None
    expected_recoverable_minor: int | None
    recommended_action: str | None
    confidence: float | None
    opened_at: datetime


class RecoveryCaseListResponse(PaginatedResponse):
    items: list[RecoveryCaseListItem]


class CaseCore(BaseModel):
    id: UUID
    case_type: str
    status: str
    amount_at_risk_minor: int
    currency: str
    failure_category: str | None
    opened_at: datetime
    last_transition_at: datetime
    version: int


class FailureEvidence(BaseModel):
    error_code: str | None = None
    error_reason: str | None = None
    error_source: str | None = None
    error_step: str | None = None


class SourceTransaction(BaseModel):
    type: str = "TRANSACTION"
    transaction_id: UUID
    provider_payment_id: str | None
    payment_method: str | None
    provider_status: str
    failure_evidence: FailureEvidence


class SourceSubscription(BaseModel):
    type: str = "SUBSCRIPTION"
    subscription_id: UUID
    provider_subscription_id: str
    provider_status: str
    failure_evidence: dict[str, Any] = Field(default_factory=dict)


class RecommendationFactor(BaseModel):
    code: str
    impact: str
    source: str


class RecommendationCandidate(BaseModel):
    action_type: str
    rank: int
    success_probability: float
    expected_recovered_minor: int
    expected_value_minor: int
    policy_eligible: bool
    requires_approval: bool
    policy_reasons: list[str]
    factors: list[RecommendationFactor]


class StructuredExplanation(BaseModel):
    summary: str
    evidence: list[str]
    safety: list[str]


class CaseAnalysis(BaseModel):
    analysis_run_id: UUID
    model_version: str
    feature_schema_version: str
    selected_action: str
    confidence: float
    candidates: list[RecommendationCandidate]
    structured_explanation: StructuredExplanation


class LatestAction(BaseModel):
    id: UUID
    action_type: str
    status: str
    attempt_number: int
    requires_approval: bool
    scheduled_for: datetime | None
    executed_at: datetime | None
    provider_reference: str | None
    provider_status: str | None
    # Durable surface for a successfully created Payment Link. The
    # create-action response (CreateRecoveryActionResponse.customer_action)
    # only exists for the immediate, non-approval execution path; an action
    # that went through approve_action never returned it at all, so an
    # operator approving a high-value case never saw the link. This field is
    # populated the same way for both paths and survives a page reload.
    customer_action: CustomerActionResponse | None = None


class CaseOutcome(BaseModel):
    outcome: str
    recovered_amount_minor: int
    recovered_payment_id: str | None
    verification_source: str
    recovered_at: datetime | None
    time_to_recovery_seconds: int | None


class RecoveryCaseDetailResponse(BaseModel):
    case: CaseCore
    customer: CustomerDetail
    source: SourceTransaction | SourceSubscription
    analysis: CaseAnalysis | None
    latest_action: LatestAction | None
    outcome: CaseOutcome | None
