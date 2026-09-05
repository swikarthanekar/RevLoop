from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.capabilities import ActionExecutionMode
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


class ERVBreakdownResponse(BaseModel):
    """Component arithmetic for one candidate's expected value.

    `expected_recovered_minor` less every penalty equals `expected_value_minor`
    exactly; the server refuses to emit this object at all when the stored
    components do not reconcile, so a client can render the subtraction without
    checking it.
    """

    expected_recovered_minor: int
    action_cost_minor: int
    fatigue_penalty_minor: int
    operational_risk_penalty_minor: int
    delay_penalty_minor: int
    expected_value_minor: int


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
    #: Derived from `action_type` on read rather than stored per row, because
    #: capability is a property of the action type and of this deployment, not
    #: of a historical analysis. Deriving it means a row written before the
    #: capability registry existed still reports the truth today, and there is
    #: no persisted copy that can go stale.
    execution_mode: ActionExecutionMode
    advisory_reason_code: str | None = None
    advisory_reason: str | None = None
    #: The arithmetic behind `expected_value_minor`, when it was persisted.
    #: Absent for rows written before the components were stored -- a client
    #: must then omit the breakdown rather than reconstruct it.
    erv_breakdown: ERVBreakdownResponse | None = None


class StructuredExplanation(BaseModel):
    summary: str
    evidence: list[str]
    safety: list[str]


class SelectedActionPolicy(BaseModel):
    """The policy verdict the executor will reach for `selected_action`, now.

    Distinct from the matching fields on `RecommendationCandidate`, which
    record what policy decided when the analysis ran. Only this one predicts
    what pressing Execute actually does, so it is what the UI must show when it
    tells someone whether their click executes or files an approval request.

    Absent when the organization has no policy row, in which case a client
    should say nothing about approval rather than guess.
    """

    eligible: bool
    requires_approval: bool
    reasons: list[str]


class CaseAnalysis(BaseModel):
    analysis_run_id: UUID
    model_version: str
    feature_schema_version: str
    #: The action the Execute control targets. Always one RevLoop can perform.
    selected_action: str
    confidence: float
    #: The model's actual top-ranked action, which may be advisory and so may
    #: differ from `selected_action`. Served explicitly rather than left for the
    #: client to infer from the candidate list, so the UI never has to
    #: reimplement the selection rule to explain the difference.
    top_ranked_action: str
    candidates: list[RecommendationCandidate]
    structured_explanation: StructuredExplanation
    #: Re-evaluated on read, not read back from the recommendation row. See
    #: `SelectedActionPolicy`.
    selected_action_policy: SelectedActionPolicy | None = None


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
