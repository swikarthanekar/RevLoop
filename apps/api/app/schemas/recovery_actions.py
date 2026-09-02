"""Recovery action API schemas (Prompt 16)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import RecoveryActionType


class CreateRecoveryActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_run_id: UUID
    action_type: RecoveryActionType


class RecoveryActionSummary(BaseModel):
    id: UUID
    action_type: RecoveryActionType
    status: str
    requires_approval: bool
    provider_reference: str | None
    scheduled_for: datetime | None


class CustomerActionResponse(BaseModel):
    type: str
    url: str


class CreateRecoveryActionResponse(BaseModel):
    action: RecoveryActionSummary
    case_status: str
    customer_action: CustomerActionResponse | None = None


class ApproveRecoveryActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_case_version: int = Field(ge=1)


class ApproveRecoveryActionResponse(BaseModel):
    action_id: UUID
    action_status: str
    case_status: str


class RejectRecoveryActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=500)
    reanalyze: bool = True


class RejectRecoveryActionResponse(BaseModel):
    action_id: UUID
    action_status: str
    case_status: str
