"""Workflow-specific exceptions for recovery case transitions."""

from __future__ import annotations

from uuid import UUID


class WorkflowError(Exception):
    """Base class for workflow transition errors."""


class InvalidTransitionError(WorkflowError):
    def __init__(
        self,
        *,
        current_status: str,
        event: str,
        message: str | None = None,
    ) -> None:
        self.current_status = current_status
        self.event = event
        self.message = message or (
            f"Transition event {event} is not allowed from state {current_status}."
        )
        super().__init__(self.message)


class TerminalStateError(WorkflowError):
    def __init__(self, *, current_status: str, event: str) -> None:
        self.current_status = current_status
        self.event = event
        self.message = f"Case in terminal state {current_status} cannot accept event {event}."
        super().__init__(self.message)


class StaleVersionError(WorkflowError):
    def __init__(
        self,
        *,
        case_id: UUID,
        expected_version: int,
        actual_version: int | None = None,
    ) -> None:
        self.case_id = case_id
        self.expected_version = expected_version
        self.actual_version = actual_version
        self.message = (
            f"Stale version for case {case_id}: expected {expected_version}, "
            f"actual {actual_version}."
        )
        super().__init__(self.message)


class MissingOutcomeError(WorkflowError):
    def __init__(self, *, case_id: UUID) -> None:
        self.case_id = case_id
        self.message = (
            f"RecoveryOutcome is required before transitioning case {case_id} to RECOVERED."
        )
        super().__init__(self.message)


class MissingEvidenceError(WorkflowError):
    def __init__(self, *, event: str, missing: list[str]) -> None:
        self.event = event
        self.missing = missing
        self.message = (
            f"Transition event {event} is missing required evidence: {', '.join(missing)}."
        )
        super().__init__(self.message)


class CaseNotFoundError(WorkflowError):
    def __init__(self, *, case_id: UUID, organization_id: UUID) -> None:
        self.case_id = case_id
        self.organization_id = organization_id
        self.message = f"Recovery case {case_id} was not found for organization {organization_id}."
        super().__init__(self.message)
