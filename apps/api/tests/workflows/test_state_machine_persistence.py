"""Optimistic concurrency and audit persistence tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.domain.enums import AuditActorType, RecoveryCaseStatus
from app.repositories.audit_logs import AuditLogWorkflowRepository
from app.workflows.events import RecoveryEvent
from app.workflows.exceptions import StaleVersionError
from app.workflows.schemas import TransitionContext
from app.workflows.state_machine import RecoveryCaseStateMachine, resolve_verified_success
from tests.workflows.helpers import (
    create_case,
    create_customer,
    create_organization,
    create_recovered_outcome,
)

UTC = datetime.now(timezone.utc)


def _context(org_id: uuid.UUID) -> TransitionContext:
    return TransitionContext(
        organization_id=org_id,
        actor_type=AuditActorType.SYSTEM,
        actor_id="workflow-test",
        occurred_at=UTC,
    )


def test_stale_version_fails_without_mutation(workflow_session) -> None:
    org = create_organization(workflow_session)
    customer = create_customer(workflow_session, organization_id=org.id)
    case = create_case(workflow_session, organization_id=org.id, customer_id=customer.id)

    machine = RecoveryCaseStateMachine()
    with pytest.raises(StaleVersionError):
        machine.transition_case(
            workflow_session,
            case_id=case.id,
            organization_id=org.id,
            expected_version=99,
            event=RecoveryEvent.ANALYSIS_REQUESTED,
            context=_context(org.id),
        )

    workflow_session.refresh(case)
    assert case.version == 1
    assert case.status == RecoveryCaseStatus.DETECTED.value
    assert (
        AuditLogWorkflowRepository().count_case_audits(
            workflow_session,
            case_id=case.id,
            organization_id=org.id,
        )
        == 0
    )


def test_successful_transition_increments_version_once(workflow_session) -> None:
    org = create_organization(workflow_session)
    customer = create_customer(workflow_session, organization_id=org.id)
    case = create_case(workflow_session, organization_id=org.id, customer_id=customer.id)

    machine = RecoveryCaseStateMachine()
    result = machine.transition_case(
        workflow_session,
        case_id=case.id,
        organization_id=org.id,
        expected_version=1,
        event=RecoveryEvent.ANALYSIS_REQUESTED,
        context=_context(org.id),
    )

    workflow_session.refresh(case)
    assert result.previous_version == 1
    assert result.new_version == 2
    assert case.version == 2


def test_duplicate_retry_with_stale_version_does_not_create_duplicate_audit(
    workflow_session,
) -> None:
    org = create_organization(workflow_session)
    customer = create_customer(workflow_session, organization_id=org.id)
    case = create_case(workflow_session, organization_id=org.id, customer_id=customer.id)

    machine = RecoveryCaseStateMachine()
    machine.transition_case(
        workflow_session,
        case_id=case.id,
        organization_id=org.id,
        expected_version=1,
        event=RecoveryEvent.ANALYSIS_REQUESTED,
        context=_context(org.id),
    )

    with pytest.raises(StaleVersionError):
        machine.transition_case(
            workflow_session,
            case_id=case.id,
            organization_id=org.id,
            expected_version=1,
            event=RecoveryEvent.ANALYSIS_REQUESTED,
            context=_context(org.id),
        )

    assert (
        AuditLogWorkflowRepository().count_case_audits(
            workflow_session,
            case_id=case.id,
            organization_id=org.id,
        )
        == 1
    )


def test_audit_record_contains_transition_metadata(workflow_session) -> None:
    org = create_organization(workflow_session)
    customer = create_customer(workflow_session, organization_id=org.id)
    case = create_case(workflow_session, organization_id=org.id, customer_id=customer.id)

    machine = RecoveryCaseStateMachine()
    result = machine.transition_case(
        workflow_session,
        case_id=case.id,
        organization_id=org.id,
        expected_version=1,
        event=RecoveryEvent.ANALYSIS_REQUESTED,
        context=_context(org.id),
    )

    from sqlalchemy import select

    from app.models.audit_log import AuditLog

    audit = workflow_session.execute(
        select(AuditLog).where(AuditLog.id == result.audit_log_id)
    ).scalar_one()

    assert audit.case_id == case.id
    assert audit.organization_id == org.id
    assert audit.evidence["previous_status"] == RecoveryCaseStatus.DETECTED.value
    assert audit.evidence["new_status"] == RecoveryCaseStatus.ANALYZING.value
    assert audit.evidence["transition_event"] == RecoveryEvent.ANALYSIS_REQUESTED.value
    assert "authorization" not in audit.evidence
    assert audit.evidence["previous_version"] == 1
    assert audit.evidence["new_version"] == 2


def test_resolve_verified_success_from_scheduled(workflow_session) -> None:
    org = create_organization(workflow_session)
    customer = create_customer(workflow_session, organization_id=org.id)
    case = create_case(
        workflow_session,
        organization_id=org.id,
        customer_id=customer.id,
        status=RecoveryCaseStatus.SCHEDULED,
    )
    create_recovered_outcome(workflow_session, organization_id=org.id, case_id=case.id)

    result = resolve_verified_success(
        workflow_session,
        case_id=case.id,
        organization_id=org.id,
        expected_version=case.version,
        context=_context(org.id),
    )

    workflow_session.refresh(case)
    assert result.new_status == RecoveryCaseStatus.RECOVERED
    assert case.status == RecoveryCaseStatus.RECOVERED.value
    assert case.resolved_at is not None


def test_resolve_verified_success_from_detected(workflow_session) -> None:
    org = create_organization(workflow_session)
    customer = create_customer(workflow_session, organization_id=org.id)
    case = create_case(workflow_session, organization_id=org.id, customer_id=customer.id)
    create_recovered_outcome(workflow_session, organization_id=org.id, case_id=case.id)

    result = resolve_verified_success(
        workflow_session,
        case_id=case.id,
        organization_id=org.id,
        expected_version=case.version,
        context=_context(org.id),
    )

    assert result.new_status == RecoveryCaseStatus.RECOVERED


def test_resolve_verified_success_cannot_revive_failed(workflow_session) -> None:
    org = create_organization(workflow_session)
    customer = create_customer(workflow_session, organization_id=org.id)
    case = create_case(
        workflow_session,
        organization_id=org.id,
        customer_id=customer.id,
        status=RecoveryCaseStatus.FAILED,
    )
    create_recovered_outcome(workflow_session, organization_id=org.id, case_id=case.id)

    from app.workflows.exceptions import TerminalStateError

    with pytest.raises(TerminalStateError):
        resolve_verified_success(
            workflow_session,
            case_id=case.id,
            organization_id=org.id,
            expected_version=case.version,
            context=_context(org.id),
        )
