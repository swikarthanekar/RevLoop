"""Contracts for the read-only recovery simulator.

The simulator answers one question interactively: *given a hypothetical failed
payment, what would RevLoop do and why?* It runs the production decision path --
candidate generation, the frozen model, ERV, the policy engine, ranking and
capability-aware selection -- over a scenario supplied in the request instead of
a persisted case.

It is strictly read-only. No case is created, no recommendation is stored, no
action is executed and no provider is contacted. That is what makes it safe to
hand to someone during a live demo: nothing they do to it can disturb the
tenant.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.domain.capabilities import ActionExecutionMode
from app.domain.enums import CaseType, FailureCategory
from app.recovery.schemas import PaymentMethodCategory

#: Bounds exist so a scenario stays inside the range the model was trained on
#: (`scripts/ml/common.py`). Outside it, a probability is extrapolation dressed
#: as a prediction, and the honest answer is to refuse rather than to render a
#: confident-looking number.
MAX_AMOUNT_MINOR = 100_000_00
MAX_HOURS_SINCE_FAILURE = 720.0


class SimulationRequest(BaseModel):
    """A hypothetical failed payment to score."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    amount_minor: int = Field(ge=100, le=MAX_AMOUNT_MINOR)
    failure_category: FailureCategory
    case_type: CaseType = CaseType.PAYMENT_FAILURE
    payment_method: PaymentMethodCategory = "upi"
    customer_segment: str = Field(default="REGULAR", max_length=32)

    hours_since_failure: float = Field(default=2.0, ge=0.0, le=MAX_HOURS_SINCE_FAILURE)
    retry_count_provider: int = Field(default=0, ge=0, le=10)
    recovery_attempts_so_far: int = Field(default=0, ge=0, le=10)
    contacts_last_24h: int = Field(default=0, ge=0, le=10)

    customer_tenure_days: float = Field(default=180.0, ge=0.0, le=3650.0)
    lifetime_value_minor: int = Field(default=50_000_00, ge=0, le=1_000_000_00)
    payment_success_rate_90d: float = Field(default=0.8, ge=0.0, le=1.0)
    successful_payments_90d: int = Field(default=8, ge=0, le=500)
    failed_payments_30d: int = Field(default=1, ge=0, le=500)

    rail_degraded: bool = False
    same_method_recent_success: bool = True
    alternate_method_recent_success: bool = True

    #: Subscription scenarios route through a different candidate matrix, so
    #: the provider's own state matters.
    subscription_status: str | None = Field(default=None, max_length=32)
    provider_retries_active: bool = False


class SimulatedCandidate(BaseModel):
    """One scored action, with the arithmetic and the policy verdict."""

    model_config = ConfigDict(frozen=True)

    action_type: str
    rank: int
    success_probability: float
    confidence: float

    expected_recovered_minor: int
    action_cost_minor: int
    fatigue_penalty_minor: int
    operational_risk_penalty_minor: int
    delay_penalty_minor: int
    expected_value_minor: int

    policy_eligible: bool
    requires_approval: bool
    policy_reasons: list[str]

    execution_mode: ActionExecutionMode
    advisory_reason: str | None = None

    #: True for the action the engine would execute. Exactly one candidate has
    #: this set, or none when no eligible executable action exists.
    selected: bool = False


class SimulationResponse(BaseModel):
    model_config = ConfigDict(frozen=True, protected_namespaces=())

    #: Never a real case. Stated in the payload so a client cannot present
    #: simulator output as a recovery that happened.
    data_source: str = "INTERACTIVE_SIMULATION"

    selected_action: str | None
    top_ranked_action: str | None
    candidates: list[SimulatedCandidate]

    currency: str
    amount_at_risk_minor: int

    #: Which model produced the probabilities, so the page can attribute them.
    model_version: str
    model_family: str
    feature_schema_version: str
    #: "model" or "fallback" -- surfaced rather than hidden, because a
    #: heuristic fallback probability must not be presented as a model output.
    inference_source: str

    #: The merchant policy actually in force, so a viewer can see why an action
    #: needs approval or is blocked.
    policy_auto_action_limit_minor: int
    policy_minimum_auto_confidence: float
