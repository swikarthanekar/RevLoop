"""Transition registry completeness tests."""

from __future__ import annotations

from app.domain.enums import RecoveryCaseStatus
from app.workflows.events import RecoveryEvent
from app.workflows.state_machine import TRANSITION_REGISTRY, lookup_transition

# Authoritative transitions from STATE_MACHINE.md section 3 plus resolve_if_paid (section 9).
DOCUMENTED_TRANSITIONS: tuple[tuple[RecoveryCaseStatus, RecoveryEvent, RecoveryCaseStatus], ...] = (
    (RecoveryCaseStatus.DETECTED, RecoveryEvent.ANALYSIS_REQUESTED, RecoveryCaseStatus.ANALYZING),
    (
        RecoveryCaseStatus.ANALYZING,
        RecoveryEvent.ANALYSIS_COMPLETED,
        RecoveryCaseStatus.RECOMMENDED,
    ),
    (
        RecoveryCaseStatus.ANALYZING,
        RecoveryEvent.ANALYSIS_TERMINAL_FAILURE,
        RecoveryCaseStatus.FAILED,
    ),
    (
        RecoveryCaseStatus.RECOMMENDED,
        RecoveryEvent.APPROVAL_REQUIRED,
        RecoveryCaseStatus.AWAITING_APPROVAL,
    ),
    (RecoveryCaseStatus.RECOMMENDED, RecoveryEvent.ACTION_SCHEDULED, RecoveryCaseStatus.SCHEDULED),
    (RecoveryCaseStatus.RECOMMENDED, RecoveryEvent.AUTO_EXECUTE, RecoveryCaseStatus.EXECUTING),
    (RecoveryCaseStatus.RECOMMENDED, RecoveryEvent.STOP_SELECTED, RecoveryCaseStatus.STOPPED),
    (
        RecoveryCaseStatus.AWAITING_APPROVAL,
        RecoveryEvent.APPROVED_NOW,
        RecoveryCaseStatus.EXECUTING,
    ),
    (
        RecoveryCaseStatus.AWAITING_APPROVAL,
        RecoveryEvent.APPROVED_LATER,
        RecoveryCaseStatus.SCHEDULED,
    ),
    (
        RecoveryCaseStatus.AWAITING_APPROVAL,
        RecoveryEvent.APPROVAL_REJECTED_REANALYZE,
        RecoveryCaseStatus.ANALYZING,
    ),
    (
        RecoveryCaseStatus.AWAITING_APPROVAL,
        RecoveryEvent.APPROVAL_REJECTED_STOP,
        RecoveryCaseStatus.STOPPED,
    ),
    (RecoveryCaseStatus.SCHEDULED, RecoveryEvent.REEVALUATION_DUE, RecoveryCaseStatus.ANALYZING),
    (RecoveryCaseStatus.SCHEDULED, RecoveryEvent.ACTION_DUE, RecoveryCaseStatus.EXECUTING),
    (RecoveryCaseStatus.SCHEDULED, RecoveryEvent.PAYMENT_VERIFIED, RecoveryCaseStatus.RECOVERED),
    (RecoveryCaseStatus.SCHEDULED, RecoveryEvent.SCHEDULE_CANCELLED, RecoveryCaseStatus.STOPPED),
    (
        RecoveryCaseStatus.EXECUTING,
        RecoveryEvent.ACTION_ACCEPTED_OR_UNKNOWN,
        RecoveryCaseStatus.WAITING_FOR_OUTCOME,
    ),
    (
        RecoveryCaseStatus.EXECUTING,
        RecoveryEvent.ACTION_FAILED_REANALYZE,
        RecoveryCaseStatus.ANALYZING,
    ),
    (
        RecoveryCaseStatus.EXECUTING,
        RecoveryEvent.TERMINAL_ACTION_FAILURE,
        RecoveryCaseStatus.FAILED,
    ),
    (RecoveryCaseStatus.EXECUTING, RecoveryEvent.PAYMENT_VERIFIED, RecoveryCaseStatus.RECOVERED),
    (
        RecoveryCaseStatus.WAITING_FOR_OUTCOME,
        RecoveryEvent.PAYMENT_VERIFIED,
        RecoveryCaseStatus.RECOVERED,
    ),
    (
        RecoveryCaseStatus.WAITING_FOR_OUTCOME,
        RecoveryEvent.NEGATIVE_OUTCOME_OR_TIMEOUT,
        RecoveryCaseStatus.ANALYZING,
    ),
    (
        RecoveryCaseStatus.WAITING_FOR_OUTCOME,
        RecoveryEvent.RECOVERY_EXHAUSTED,
        RecoveryCaseStatus.FAILED,
    ),
    (
        RecoveryCaseStatus.WAITING_FOR_OUTCOME,
        RecoveryEvent.STOPPING_RULE_MET,
        RecoveryCaseStatus.STOPPED,
    ),
    (RecoveryCaseStatus.DETECTED, RecoveryEvent.PAYMENT_VERIFIED, RecoveryCaseStatus.RECOVERED),
    (RecoveryCaseStatus.ANALYZING, RecoveryEvent.PAYMENT_VERIFIED, RecoveryCaseStatus.RECOVERED),
    (RecoveryCaseStatus.RECOMMENDED, RecoveryEvent.PAYMENT_VERIFIED, RecoveryCaseStatus.RECOVERED),
    (
        RecoveryCaseStatus.AWAITING_APPROVAL,
        RecoveryEvent.PAYMENT_VERIFIED,
        RecoveryCaseStatus.RECOVERED,
    ),
)


def test_every_documented_transition_exists_in_registry() -> None:
    for source, event, target in DOCUMENTED_TRANSITIONS:
        definition = lookup_transition(source, event)
        assert definition is not None, f"Missing transition: {source.value} + {event.value}"
        assert definition.target == target


def test_registry_has_no_undocumented_transitions() -> None:
    documented_keys = {(source, event) for source, event, _target in DOCUMENTED_TRANSITIONS}
    registry_keys = set(TRANSITION_REGISTRY.keys())
    undocumented = registry_keys - documented_keys
    assert not undocumented, f"Undocumented transitions: {undocumented}"


def test_registry_size_matches_documented_count() -> None:
    assert len(TRANSITION_REGISTRY) == len(DOCUMENTED_TRANSITIONS)
