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


class DashboardSummaryResponse(BaseModel):
    currency: str
    revenue_at_risk_minor: int
    revenue_recovered_minor: int
    baseline_recovered_minor: int
    incremental_recovered_minor: int
    recovery_rate: float = Field(ge=0.0, le=1.0)
    active_cases: int
    recovered_cases: int
    average_recovery_seconds: int | None
    recovery_trend: list[RecoveryTrendPoint]
    action_effectiveness: list[ActionEffectivenessRow]
    failure_breakdown: list[FailureBreakdownRow]
    source_label: str
