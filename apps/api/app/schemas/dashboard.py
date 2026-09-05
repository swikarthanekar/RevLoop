from pydantic import BaseModel, Field


class RecoveryTrendPoint(BaseModel):
    date: str
    at_risk_minor: int
    recovered_minor: int


class ActionEffectivenessRow(BaseModel):
    action_type: str
    attempted: int
    recovered: int
    recovery_rate: float = Field(ge=0.0, le=1.0)
    recovered_minor: int


class FailureBreakdownRow(BaseModel):
    failure_category: str
    cases: int
    amount_minor: int


class BaselineAssumption(BaseModel):
    """How `baseline_recovered_minor` was arrived at.

    Served from the server rather than written into UI copy, so the disclosure
    cannot drift from the constant it describes. `incremental_recovered_minor`
    is a MODELLED counterfactual, not a measured control group: there is no
    holdout of untreated cases in this dataset. Presenting it as a flat
    comparison without saying so would invite a reasonable "how do you know?"
    that the number cannot answer.
    """

    #: Machine-readable so a client can style it as an assumption, not a fact.
    kind: str = "MODELLED_COUNTERFACTUAL"
    #: The assumed recovery rate for the naive policy, as a fraction.
    naive_recovery_rate: float
    #: Which rank-1 actions count as the naive policy's own choice.
    naive_actions: list[str]
    #: One sentence, written for a reader who will ask how it was derived.
    description: str


class DashboardSummaryResponse(BaseModel):
    currency: str
    revenue_at_risk_minor: int
    revenue_recovered_minor: int
    baseline_recovered_minor: int
    incremental_recovered_minor: int
    #: Disclosure for the two fields above.
    baseline_assumption: BaselineAssumption
    recovery_rate: float = Field(ge=0.0, le=1.0)
    active_cases: int
    recovered_cases: int
    average_recovery_seconds: int | None
    recovery_trend: list[RecoveryTrendPoint]
    action_effectiveness: list[ActionEffectivenessRow]
    failure_breakdown: list[FailureBreakdownRow]
    source_label: str
