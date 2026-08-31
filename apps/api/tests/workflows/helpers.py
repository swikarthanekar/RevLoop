"""Helpers for workflow persistence tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.domain.enums import CaseType, RecoveryCaseStatus, RecoveryOutcomeType, VerificationSource
from app.models.customer import Customer
from app.models.organization import Organization
from app.models.recovery_case import RecoveryCase
from app.models.recovery_outcome import RecoveryOutcome
from app.models.transaction import Transaction


def create_organization(session: Session, *, org_id: uuid.UUID | None = None) -> Organization:
    organization = Organization(
        id=org_id or uuid.uuid4(),
        name="Workflow Test Org",
        currency="INR",
        automation_enabled=True,
    )
    session.add(organization)
    session.flush()
    return organization


def create_customer(
    session: Session,
    *,
    organization_id: uuid.UUID,
    customer_id: uuid.UUID | None = None,
) -> Customer:
    customer = Customer(
        id=customer_id or uuid.uuid4(),
        organization_id=organization_id,
        external_id=f"wf-customer-{uuid.uuid4().hex[:8]}",
        display_name="Workflow Test Customer",
        segment="REGULAR",
        lifetime_value_minor=100000,
        is_synthetic=True,
    )
    session.add(customer)
    session.flush()
    return customer


def create_transaction(
    session: Session,
    *,
    organization_id: uuid.UUID,
    customer_id: uuid.UUID,
    transaction_id: uuid.UUID | None = None,
) -> Transaction:
    transaction = Transaction(
        id=transaction_id or uuid.uuid4(),
        organization_id=organization_id,
        customer_id=customer_id,
        provider="razorpay",
        provider_payment_id=f"pay_wf_{uuid.uuid4().hex[:12]}",
        amount_minor=499900,
        currency="INR",
        status="failed",
        payment_method="UPI",
        is_synthetic=True,
    )
    session.add(transaction)
    session.flush()
    return transaction


def create_case(
    session: Session,
    *,
    organization_id: uuid.UUID,
    customer_id: uuid.UUID,
    status: RecoveryCaseStatus = RecoveryCaseStatus.DETECTED,
    version: int = 1,
    opened_at: datetime | None = None,
    case_id: uuid.UUID | None = None,
) -> RecoveryCase:
    now = opened_at or datetime.now(timezone.utc)
    transaction = create_transaction(
        session,
        organization_id=organization_id,
        customer_id=customer_id,
    )
    case = RecoveryCase(
        id=case_id or uuid.uuid4(),
        organization_id=organization_id,
        customer_id=customer_id,
        transaction_id=transaction.id,
        source_event_key=f"workflow-test:{uuid.uuid4()}",
        case_type=CaseType.PAYMENT_FAILURE.value,
        amount_at_risk_minor=499900,
        currency="INR",
        failure_category="INSUFFICIENT_FUNDS",
        status=status.value,
        opened_at=now,
        last_transition_at=now,
        version=version,
    )
    session.add(case)
    session.flush()
    return case


def create_recovered_outcome(
    session: Session,
    *,
    organization_id: uuid.UUID,
    case_id: uuid.UUID,
    recovered_amount_minor: int = 499900,
) -> RecoveryOutcome:
    outcome = RecoveryOutcome(
        organization_id=organization_id,
        case_id=case_id,
        outcome=RecoveryOutcomeType.RECOVERED.value,
        recovered_amount_minor=recovered_amount_minor,
        recovered_payment_id=f"pay_{uuid.uuid4().hex[:12]}",
        verification_source=VerificationSource.SIMULATED_BATCH.value,
        recovered_at=datetime.now(timezone.utc),
        time_to_recovery_seconds=3600,
    )
    session.add(outcome)
    session.flush()
    return outcome
