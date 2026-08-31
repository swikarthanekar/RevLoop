"""Authoritative RecoveryCase workflow state machine."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.domain.enums import RecoveryCaseStatus
from app.repositories.audit_logs import AuditLogWorkflowRepository
from app.repositories.recovery_cases import RecoveryCaseWorkflowRepository
from app.workflows.events import RecoveryEvent
from app.workflows.exceptions import (
    CaseNotFoundError,
    InvalidTransitionError,
    MissingEvidenceError,
    MissingOutcomeError,
    StaleVersionError,
    TerminalStateError,
)
from app.workflows.schemas import TransitionContext, TransitionDefinition, TransitionResult

TERMINAL_STATUSES = frozenset(
    {
        RecoveryCaseStatus.RECOVERED,
        RecoveryCaseStatus.FAILED,
        RecoveryCaseStatus.STOPPED,
    }
)

EVIDENCE_CASE_EXISTS = "case_exists"
EVIDENCE_ANALYSIS_RUN = "analysis_run"
EVIDENCE_ACTION = "action"
EVIDENCE_SCHEDULE = "schedule"
EVIDENCE_APPROVER = "approver"
EVIDENCE_REASON = "reason"
EVIDENCE_REJECTION = "rejection"
EVIDENCE_OUTCOME = "outcome"
EVIDENCE_ACTION_RESULT = "action_result"

_SENSITIVE_EVIDENCE_KEYS = frozenset(
    {
        "authorization",
        "authorization_header",
        "api_key",
        "secret",
        "password",
        "token",
        "credentials",
        "stack_trace",
        "traceback",
        "raw_payload",
        "webhook_secret",
    }
)


def _transition(
    source: RecoveryCaseStatus,
    event: RecoveryEvent,
    target: RecoveryCaseStatus,
    audit_event_type: str,
    required_evidence: frozenset[str],
) -> TransitionDefinition:
    return TransitionDefinition(
        source=source,
        event=event,
        target=target,
        audit_event_type=audit_event_type,
        required_evidence=required_evidence,
    )


_TRANSITION_DEFINITIONS: tuple[TransitionDefinition, ...] = (
    _transition(
        RecoveryCaseStatus.DETECTED,
        RecoveryEvent.ANALYSIS_REQUESTED,
        RecoveryCaseStatus.ANALYZING,
        "ANALYSIS_REQUESTED",
        frozenset({EVIDENCE_CASE_EXISTS}),
    ),
    _transition(
        RecoveryCaseStatus.ANALYZING,
        RecoveryEvent.ANALYSIS_COMPLETED,
        RecoveryCaseStatus.RECOMMENDED,
        "ANALYSIS_COMPLETED",
        frozenset({EVIDENCE_ANALYSIS_RUN}),
    ),
    _transition(
        RecoveryCaseStatus.ANALYZING,
        RecoveryEvent.ANALYSIS_TERMINAL_FAILURE,
        RecoveryCaseStatus.FAILED,
        "CASE_FAILED",
        frozenset({EVIDENCE_REASON}),
    ),
    _transition(
        RecoveryCaseStatus.RECOMMENDED,
        RecoveryEvent.APPROVAL_REQUIRED,
        RecoveryCaseStatus.AWAITING_APPROVAL,
        "APPROVAL_REQUESTED",
        frozenset({EVIDENCE_ACTION, EVIDENCE_ANALYSIS_RUN}),
    ),
    _transition(
        RecoveryCaseStatus.RECOMMENDED,
        RecoveryEvent.ACTION_SCHEDULED,
        RecoveryCaseStatus.SCHEDULED,
        "ACTION_SCHEDULED",
        frozenset({EVIDENCE_ACTION, EVIDENCE_SCHEDULE}),
    ),
    _transition(
        RecoveryCaseStatus.RECOMMENDED,
        RecoveryEvent.AUTO_EXECUTE,
        RecoveryCaseStatus.EXECUTING,
        "ACTION_EXECUTION_STARTED",
        frozenset({EVIDENCE_ACTION}),
    ),
    _transition(
        RecoveryCaseStatus.RECOMMENDED,
        RecoveryEvent.STOP_SELECTED,
        RecoveryCaseStatus.STOPPED,
        "CASE_STOPPED",
        frozenset({EVIDENCE_REASON}),
    ),
    _transition(
        RecoveryCaseStatus.AWAITING_APPROVAL,
        RecoveryEvent.APPROVED_NOW,
        RecoveryCaseStatus.EXECUTING,
        "ACTION_EXECUTION_STARTED",
        frozenset({EVIDENCE_APPROVER, EVIDENCE_ACTION}),
    ),
    _transition(
        RecoveryCaseStatus.AWAITING_APPROVAL,
        RecoveryEvent.APPROVED_LATER,
        RecoveryCaseStatus.SCHEDULED,
        "ACTION_SCHEDULED",
        frozenset({EVIDENCE_APPROVER, EVIDENCE_ACTION, EVIDENCE_SCHEDULE}),
    ),
    _transition(
        RecoveryCaseStatus.AWAITING_APPROVAL,
        RecoveryEvent.APPROVAL_REJECTED_REANALYZE,
        RecoveryCaseStatus.ANALYZING,
        "APPROVAL_REJECTED",
        frozenset({EVIDENCE_REJECTION, EVIDENCE_REASON}),
    ),
    _transition(
        RecoveryCaseStatus.AWAITING_APPROVAL,
        RecoveryEvent.APPROVAL_REJECTED_STOP,
        RecoveryCaseStatus.STOPPED,
        "CASE_STOPPED",
        frozenset({EVIDENCE_REJECTION, EVIDENCE_REASON}),
    ),
    _transition(
        RecoveryCaseStatus.SCHEDULED,
        RecoveryEvent.REEVALUATION_DUE,
        RecoveryCaseStatus.ANALYZING,
        "REEVALUATION_DUE",
        frozenset({EVIDENCE_SCHEDULE}),
    ),
    _transition(
        RecoveryCaseStatus.SCHEDULED,
        RecoveryEvent.ACTION_DUE,
        RecoveryCaseStatus.EXECUTING,
        "ACTION_EXECUTION_STARTED",
        frozenset({EVIDENCE_ACTION}),
    ),
    _transition(
        RecoveryCaseStatus.SCHEDULED,
        RecoveryEvent.PAYMENT_VERIFIED,
        RecoveryCaseStatus.RECOVERED,
        "CASE_RECOVERED",
        frozenset({EVIDENCE_OUTCOME}),
    ),
    _transition(
        RecoveryCaseStatus.SCHEDULED,
        RecoveryEvent.SCHEDULE_CANCELLED,
        RecoveryCaseStatus.STOPPED,
        "CASE_STOPPED",
        frozenset({EVIDENCE_REASON}),
    ),
    _transition(
        RecoveryCaseStatus.EXECUTING,
        RecoveryEvent.ACTION_ACCEPTED_OR_UNKNOWN,
        RecoveryCaseStatus.WAITING_FOR_OUTCOME,
        "ACTION_ACCEPTED_OR_UNKNOWN",
        frozenset({EVIDENCE_ACTION_RESULT}),
    ),
    _transition(
        RecoveryCaseStatus.EXECUTING,
        RecoveryEvent.ACTION_FAILED_REANALYZE,
        RecoveryCaseStatus.ANALYZING,
        "ACTION_FAILED",
        frozenset({EVIDENCE_ACTION, EVIDENCE_REASON}),
    ),
    _transition(
        RecoveryCaseStatus.EXECUTING,
        RecoveryEvent.TERMINAL_ACTION_FAILURE,
        RecoveryCaseStatus.FAILED,
        "CASE_FAILED",
        frozenset({EVIDENCE_REASON}),
    ),
    _transition(
        RecoveryCaseStatus.EXECUTING,
        RecoveryEvent.PAYMENT_VERIFIED,
        RecoveryCaseStatus.RECOVERED,
        "CASE_RECOVERED",
        frozenset({EVIDENCE_OUTCOME}),
    ),
    _transition(
        RecoveryCaseStatus.WAITING_FOR_OUTCOME,
        RecoveryEvent.PAYMENT_VERIFIED,
        RecoveryCaseStatus.RECOVERED,
        "CASE_RECOVERED",
        frozenset({EVIDENCE_OUTCOME}),
    ),
    _transition(
        RecoveryCaseStatus.WAITING_FOR_OUTCOME,
        RecoveryEvent.NEGATIVE_OUTCOME_OR_TIMEOUT,
        RecoveryCaseStatus.ANALYZING,
        "NEGATIVE_OUTCOME_OR_TIMEOUT",
        frozenset({EVIDENCE_REASON}),
    ),
    _transition(
        RecoveryCaseStatus.WAITING_FOR_OUTCOME,
        RecoveryEvent.RECOVERY_EXHAUSTED,
        RecoveryCaseStatus.FAILED,
        "CASE_FAILED",
        frozenset({EVIDENCE_REASON}),
    ),
    _transition(
        RecoveryCaseStatus.WAITING_FOR_OUTCOME,
        RecoveryEvent.STOPPING_RULE_MET,
        RecoveryCaseStatus.STOPPED,
        "CASE_STOPPED",
        frozenset({EVIDENCE_REASON}),
    ),
    _transition(
        RecoveryCaseStatus.DETECTED,
        RecoveryEvent.PAYMENT_VERIFIED,
        RecoveryCaseStatus.RECOVERED,
        "CASE_RECOVERED",
        frozenset({EVIDENCE_OUTCOME}),
    ),
    _transition(
        RecoveryCaseStatus.ANALYZING,
        RecoveryEvent.PAYMENT_VERIFIED,
        RecoveryCaseStatus.RECOVERED,
        "CASE_RECOVERED",
        frozenset({EVIDENCE_OUTCOME}),
    ),
    _transition(
        RecoveryCaseStatus.RECOMMENDED,
        RecoveryEvent.PAYMENT_VERIFIED,
        RecoveryCaseStatus.RECOVERED,
        "CASE_RECOVERED",
        frozenset({EVIDENCE_OUTCOME}),
    ),
    _transition(
        RecoveryCaseStatus.AWAITING_APPROVAL,
        RecoveryEvent.PAYMENT_VERIFIED,
        RecoveryCaseStatus.RECOVERED,
        "CASE_RECOVERED",
        frozenset({EVIDENCE_OUTCOME}),
    ),
)

TRANSITION_REGISTRY: dict[tuple[RecoveryCaseStatus, RecoveryEvent], TransitionDefinition] = {
    (definition.source, definition.event): definition for definition in _TRANSITION_DEFINITIONS
}


def lookup_transition(
    current_status: RecoveryCaseStatus,
    event: RecoveryEvent,
) -> TransitionDefinition | None:
    return TRANSITION_REGISTRY.get((current_status, event))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sanitize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in metadata.items():
        normalized = key.lower().replace("-", "_")
        if normalized in _SENSITIVE_EVIDENCE_KEYS:
            continue
        if normalized.endswith("_secret") or normalized.endswith("_token"):
            continue
        if isinstance(value, dict):
            nested = _sanitize_metadata(value)
            if nested:
                sanitized[key] = nested
            continue
        sanitized[key] = value
    return sanitized


def _validate_context_evidence(
    definition: TransitionDefinition,
    context: TransitionContext,
) -> None:
    missing: list[str] = []
    for requirement in definition.required_evidence:
        if requirement == EVIDENCE_CASE_EXISTS:
            continue
        if requirement == EVIDENCE_ANALYSIS_RUN and context.analysis_run_id is None:
            missing.append(requirement)
        elif requirement == EVIDENCE_ACTION and context.action_id is None:
            missing.append(requirement)
        elif requirement == EVIDENCE_SCHEDULE and context.scheduled_for is None:
            missing.append(requirement)
        elif requirement == EVIDENCE_APPROVER and context.approver_id is None:
            missing.append(requirement)
        elif requirement == EVIDENCE_REASON and not (context.reason and context.reason.strip()):
            missing.append(requirement)
        elif requirement == EVIDENCE_REJECTION and not context.rejection_recorded:
            missing.append(requirement)
        elif requirement == EVIDENCE_ACTION_RESULT and context.action_id is None:
            missing.append(requirement)
    if missing:
        raise MissingEvidenceError(event=definition.event.value, missing=missing)


def _build_audit_summary(
    definition: TransitionDefinition,
    previous_status: RecoveryCaseStatus,
) -> str:
    return (
        f"Recovery case transitioned from {previous_status.value} to "
        f"{definition.target.value} via {definition.event.value}."
    )


def _build_audit_evidence(
    definition: TransitionDefinition,
    context: TransitionContext,
    *,
    previous_status: RecoveryCaseStatus,
    new_status: RecoveryCaseStatus,
    previous_version: int,
    new_version: int,
) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "transition_event": definition.event.value,
        "previous_status": previous_status.value,
        "new_status": new_status.value,
        "previous_version": previous_version,
        "new_version": new_version,
    }
    if context.analysis_run_id is not None:
        evidence["analysis_run_id"] = str(context.analysis_run_id)
    if context.action_id is not None:
        evidence["action_id"] = str(context.action_id)
    if context.scheduled_for is not None:
        evidence["scheduled_for"] = context.scheduled_for.isoformat()
    if context.approver_id is not None:
        evidence["approver_id"] = str(context.approver_id)
    if context.reason:
        evidence["reason"] = context.reason
    if context.rejection_recorded:
        evidence["rejection_recorded"] = True
    if context.metadata:
        evidence["metadata"] = _sanitize_metadata(context.metadata)
    return evidence


class RecoveryCaseStateMachine:
    def __init__(
        self,
        case_repo: RecoveryCaseWorkflowRepository | None = None,
        audit_repo: AuditLogWorkflowRepository | None = None,
    ) -> None:
        self._case_repo = case_repo or RecoveryCaseWorkflowRepository()
        self._audit_repo = audit_repo or AuditLogWorkflowRepository()

    def transition_case(
        self,
        session: Session,
        *,
        case_id: UUID,
        organization_id: UUID,
        expected_version: int,
        event: RecoveryEvent,
        context: TransitionContext,
    ) -> TransitionResult:
        if context.organization_id != organization_id:
            raise CaseNotFoundError(case_id=case_id, organization_id=organization_id)

        case = self._case_repo.get_case(
            session,
            case_id=case_id,
            organization_id=organization_id,
        )
        if case is None:
            raise CaseNotFoundError(case_id=case_id, organization_id=organization_id)

        current_status = RecoveryCaseStatus(case.status)
        if current_status in TERMINAL_STATUSES:
            raise TerminalStateError(current_status=current_status.value, event=event.value)

        if case.version != expected_version:
            raise StaleVersionError(
                case_id=case_id,
                expected_version=expected_version,
                actual_version=case.version,
            )

        definition = lookup_transition(current_status, event)
        if definition is None:
            raise InvalidTransitionError(current_status=current_status.value, event=event.value)

        _validate_context_evidence(definition, context)

        if definition.target == RecoveryCaseStatus.RECOVERED:
            if not self._case_repo.has_recovered_outcome(
                session,
                case_id=case_id,
                organization_id=organization_id,
            ):
                raise MissingOutcomeError(case_id=case_id)

        transition_at = context.occurred_at or _utcnow()
        resolved_at = transition_at if definition.target in TERMINAL_STATUSES else None

        rows_updated = self._case_repo.persist_transition(
            session,
            case_id=case_id,
            organization_id=organization_id,
            expected_version=expected_version,
            new_status=definition.target,
            transition_at=transition_at,
            resolved_at=resolved_at,
        )
        if rows_updated == 0:
            refreshed = self._case_repo.get_case(
                session,
                case_id=case_id,
                organization_id=organization_id,
            )
            actual_version = refreshed.version if refreshed is not None else None
            raise StaleVersionError(
                case_id=case_id,
                expected_version=expected_version,
                actual_version=actual_version,
            )

        audit = self._audit_repo.insert_transition_audit(
            session,
            organization_id=organization_id,
            case_id=case_id,
            actor_type=context.actor_type,
            actor_id=context.actor_id,
            event_type=definition.audit_event_type,
            summary=_build_audit_summary(definition, current_status),
            evidence=_build_audit_evidence(
                definition,
                context,
                previous_status=current_status,
                new_status=definition.target,
                previous_version=expected_version,
                new_version=expected_version + 1,
            ),
        )

        session.commit()

        return TransitionResult(
            case_id=case_id,
            organization_id=organization_id,
            previous_status=current_status,
            new_status=definition.target,
            previous_version=expected_version,
            new_version=expected_version + 1,
            event=event,
            audit_log_id=audit.id,
        )

    def resolve_verified_success(
        self,
        session: Session,
        *,
        case_id: UUID,
        organization_id: UUID,
        expected_version: int,
        context: TransitionContext,
    ) -> TransitionResult:
        return self.transition_case(
            session,
            case_id=case_id,
            organization_id=organization_id,
            expected_version=expected_version,
            event=RecoveryEvent.PAYMENT_VERIFIED,
            context=context,
        )


def transition_case(
    session: Session,
    *,
    case_id: UUID,
    organization_id: UUID,
    expected_version: int,
    event: RecoveryEvent,
    context: TransitionContext,
) -> TransitionResult:
    return RecoveryCaseStateMachine().transition_case(
        session,
        case_id=case_id,
        organization_id=organization_id,
        expected_version=expected_version,
        event=event,
        context=context,
    )


def resolve_verified_success(
    session: Session,
    *,
    case_id: UUID,
    organization_id: UUID,
    expected_version: int,
    context: TransitionContext,
) -> TransitionResult:
    return RecoveryCaseStateMachine().resolve_verified_success(
        session,
        case_id=case_id,
        organization_id=organization_id,
        expected_version=expected_version,
        context=context,
    )
