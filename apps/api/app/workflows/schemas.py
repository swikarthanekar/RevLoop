"""Workflow transition schemas."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from app.domain.enums import AuditActorType, RecoveryCaseStatus
from app.workflows.events import RecoveryEvent


@dataclass(frozen=True)
class TransitionContext:
    organization_id: UUID
    actor_type: AuditActorType
    actor_id: str | None = None
    occurred_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    analysis_run_id: UUID | None = None
    action_id: UUID | None = None
    scheduled_for: datetime | None = None
    approver_id: UUID | None = None
    reason: str | None = None
    rejection_recorded: bool = False


@dataclass(frozen=True)
class TransitionDefinition:
    source: RecoveryCaseStatus
    event: RecoveryEvent
    target: RecoveryCaseStatus
    audit_event_type: str
    required_evidence: frozenset[str]


@dataclass(frozen=True)
class TransitionResult:
    case_id: UUID
    organization_id: UUID
    previous_status: RecoveryCaseStatus
    new_status: RecoveryCaseStatus
    previous_version: int
    new_version: int
    event: RecoveryEvent
    audit_log_id: UUID
