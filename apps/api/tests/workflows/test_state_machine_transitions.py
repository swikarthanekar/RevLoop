"""Allowed and forbidden transition behavior tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.domain.enums import AuditActorType, RecoveryCaseStatus
from app.workflows.events import RecoveryEvent
from app.workflows.exceptions import (
    InvalidTransitionError,
    MissingEvidenceError,
    MissingOutcomeError,
    TerminalStateError,
)
from app.workflows.schemas import TransitionContext
from app.workflows.state_machine import RecoveryCaseStateMachine, lookup_transition
from tests.workflows.helpers import (
    create_case,
    create_customer,
    create_organization,
    create_recovered_outcome,
)
from tests.workflows.test_transition_registry import DOCUMENTED_TRANSITIONS

UTC = datetime.now(timezone.utc)


def _context(org_id: uuid.UUID, **kwargs) -> TransitionContext:
    return TransitionContext(
        organization_id=org_id,
        actor_type=AuditActorType.SYSTEM,
        actor_id="workflow-test",
        occurred_at=UTC,
        **kwargs,
    )


@pytest.mark.parametrize(
    ("source", "event", "target"),
    DOCUMENTED_TRANSITIONS,
)
def test_allowed_transitions_are_registered(
    source: RecoveryCaseStatus,
    event: RecoveryEvent,
    target: RecoveryCaseStatus,
) -> None:
    definition = lookup_transition(source, event)
    assert definition is not None
    assert definition.target == target


@pytest.mark.parametrize(
    ("source", "event", "target", "context_kwargs"),
    [
        (
            RecoveryCaseStatus.DETECTED,
            RecoveryEvent.ANALYSIS_REQUESTED,
            RecoveryCaseStatus.ANALYZING,
            {},
        ),
        (
            RecoveryCaseStatus.ANALYZING,
            RecoveryEvent.ANALYSIS_COMPLETED,
            RecoveryCaseStatus.RECOMMENDED,
            {"analysis_run_id": uuid.uuid4()},
        ),
        (
            RecoveryCaseStatus.ANALYZING,
            RecoveryEvent.ANALYSIS_TERMINAL_FAILURE,
            RecoveryCaseStatus.FAILED,
            {"reason": "No valid analysis path"},
        ),
        (
            RecoveryCaseStatus.RECOMMENDED,
            RecoveryEvent.STOP_SELECTED,
            RecoveryCaseStatus.STOPPED,
            {"reason": "Operator stop"},
        ),
        (
            RecoveryCaseStatus.WAITING_FOR_OUTCOME,
            RecoveryEvent.PAYMENT_VERIFIED,
            RecoveryCaseStatus.RECOVERED,
            {},
        ),
    ],
)
def test_allowed_transition_persists_state_and_audit(
    workflow_session,
    source: RecoveryCaseStatus,
    event: RecoveryEvent,
    target: RecoveryCaseStatus,
    context_kwargs: dict,
) -> None:
    org = create_organization(workflow_session)
    customer = create_customer(workflow_session, organization_id=org.id)
    case = create_case(
        workflow_session,
        organization_id=org.id,
        customer_id=customer.id,
        status=source,
    )

    if target == RecoveryCaseStatus.RECOVERED:
        create_recovered_outcome(
            workflow_session,
            organization_id=org.id,
            case_id=case.id,
        )

    if event == RecoveryEvent.ANALYSIS_COMPLETED:
        context_kwargs.setdefault("analysis_run_id", uuid.uuid4())
    if event in {RecoveryEvent.STOP_SELECTED, RecoveryEvent.ANALYSIS_TERMINAL_FAILURE}:
        context_kwargs.setdefault("reason", "test reason")

    machine = RecoveryCaseStateMachine()
    result = machine.transition_case(
        workflow_session,
        case_id=case.id,
        organization_id=org.id,
        expected_version=case.version,
        event=event,
        context=_context(org.id, **context_kwargs),
    )

    workflow_session.refresh(case)
    assert result.new_status == target
    assert case.status == target.value
    assert case.version == result.new_version
    assert result.new_version == result.previous_version + 1

    from app.repositories.audit_logs import AuditLogWorkflowRepository

    audit_count = AuditLogWorkflowRepository().count_case_audits(
        workflow_session,
        case_id=case.id,
        organization_id=org.id,
    )
    assert audit_count == 1


def test_invalid_transition_raises_and_does_not_mutate(workflow_session) -> None:
    org = create_organization(workflow_session)
    customer = create_customer(workflow_session, organization_id=org.id)
    case = create_case(workflow_session, organization_id=org.id, customer_id=customer.id)

    machine = RecoveryCaseStateMachine()
    with pytest.raises(InvalidTransitionError):
        machine.transition_case(
            workflow_session,
            case_id=case.id,
            organization_id=org.id,
            expected_version=case.version,
            event=RecoveryEvent.AUTO_EXECUTE,
            context=_context(org.id, action_id=uuid.uuid4()),
        )

    workflow_session.refresh(case)
    assert case.status == RecoveryCaseStatus.DETECTED.value
    assert case.version == 1

    from app.repositories.audit_logs import AuditLogWorkflowRepository

    assert (
        AuditLogWorkflowRepository().count_case_audits(
            workflow_session,
            case_id=case.id,
            organization_id=org.id,
        )
        == 0
    )


def test_terminal_state_rejects_transition(workflow_session) -> None:
    org = create_organization(workflow_session)
    customer = create_customer(workflow_session, organization_id=org.id)
    case = create_case(
        workflow_session,
        organization_id=org.id,
        customer_id=customer.id,
        status=RecoveryCaseStatus.RECOVERED,
    )
    create_recovered_outcome(workflow_session, organization_id=org.id, case_id=case.id)

    machine = RecoveryCaseStateMachine()
    with pytest.raises(TerminalStateError):
        machine.transition_case(
            workflow_session,
            case_id=case.id,
            organization_id=org.id,
            expected_version=case.version,
            event=RecoveryEvent.ANALYSIS_REQUESTED,
            context=_context(org.id),
        )


@pytest.mark.parametrize(
    "terminal_status",
    [
        RecoveryCaseStatus.RECOVERED,
        RecoveryCaseStatus.FAILED,
        RecoveryCaseStatus.STOPPED,
    ],
)
def test_terminal_states_are_immutable(
    workflow_session,
    terminal_status: RecoveryCaseStatus,
) -> None:
    org = create_organization(workflow_session)
    customer = create_customer(workflow_session, organization_id=org.id)
    case = create_case(
        workflow_session,
        organization_id=org.id,
        customer_id=customer.id,
        status=terminal_status,
    )
    if terminal_status == RecoveryCaseStatus.RECOVERED:
        create_recovered_outcome(workflow_session, organization_id=org.id, case_id=case.id)

    original_version = case.version
    original_updated_at = case.updated_at

    machine = RecoveryCaseStateMachine()
    with pytest.raises(TerminalStateError):
        machine.transition_case(
            workflow_session,
            case_id=case.id,
            organization_id=org.id,
            expected_version=case.version,
            event=RecoveryEvent.PAYMENT_VERIFIED,
            context=_context(org.id),
        )

    workflow_session.refresh(case)
    assert case.version == original_version
    assert case.updated_at == original_updated_at


def test_recovered_without_outcome_fails(workflow_session) -> None:
    org = create_organization(workflow_session)
    customer = create_customer(workflow_session, organization_id=org.id)
    case = create_case(
        workflow_session,
        organization_id=org.id,
        customer_id=customer.id,
        status=RecoveryCaseStatus.WAITING_FOR_OUTCOME,
    )

    machine = RecoveryCaseStateMachine()
    with pytest.raises(MissingOutcomeError):
        machine.transition_case(
            workflow_session,
            case_id=case.id,
            organization_id=org.id,
            expected_version=case.version,
            event=RecoveryEvent.PAYMENT_VERIFIED,
            context=_context(org.id),
        )

    workflow_session.refresh(case)
    assert case.status == RecoveryCaseStatus.WAITING_FOR_OUTCOME.value
    assert case.version == 1


def test_missing_evidence_fails_without_mutation(workflow_session) -> None:
    org = create_organization(workflow_session)
    customer = create_customer(workflow_session, organization_id=org.id)
    case = create_case(
        workflow_session,
        organization_id=org.id,
        customer_id=customer.id,
        status=RecoveryCaseStatus.ANALYZING,
    )

    machine = RecoveryCaseStateMachine()
    with pytest.raises(MissingEvidenceError):
        machine.transition_case(
            workflow_session,
            case_id=case.id,
            organization_id=org.id,
            expected_version=case.version,
            event=RecoveryEvent.ANALYSIS_COMPLETED,
            context=_context(org.id),
        )

    workflow_session.refresh(case)
    assert case.version == 1
