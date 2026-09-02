"""API-level Razorpay webhook tests."""

from __future__ import annotations

# ruff: noqa: E402
pytest_plugins = ["tests.integrations.razorpay.conftest"]

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.demo.constants import DEMO_ORGANIZATION_ID
from app.domain.enums import RecoveryActionStatus, RecoveryActionType, RecoveryCaseStatus
from app.models.recovery_action import RecoveryAction
from app.models.recovery_case import RecoveryCase
from app.models.recovery_outcome import RecoveryOutcome
from tests.api.conftest import DEMO_AUTH_HEADERS
from tests.demo.conftest import postgres_available
from tests.integrations.razorpay.conftest import post_webhook
from tests.integrations.razorpay.helpers import (
    build_webhook_payload,
    payment_entity,
    payment_link_entity,
    signed_request,
)
from tests.workflows.helpers import (
    create_case,
    create_customer,
    create_organization,
    create_transaction,
)

pytestmark = pytest.mark.skipif(
    not postgres_available(),
    reason="PostgreSQL not available",
)


@pytest.fixture
def webhook_session_factory(webhook_seeded_database):
    return sessionmaker(bind=webhook_seeded_database, autoflush=False, autocommit=False)


def test_payment_link_paid_correlated_success(
    webhook_client,
    webhook_session_factory,
    webhook_db_session,
) -> None:
    setup = webhook_session_factory()
    reference = "rq_corr_link_001"
    try:
        customer = create_customer(setup, organization_id=DEMO_ORGANIZATION_ID)
        case = create_case(
            setup,
            organization_id=DEMO_ORGANIZATION_ID,
            customer_id=customer.id,
            status=RecoveryCaseStatus.WAITING_FOR_OUTCOME,
        )
        action = RecoveryAction(
            organization_id=DEMO_ORGANIZATION_ID,
            case_id=case.id,
            action_type=RecoveryActionType.CREATE_PAYMENT_LINK.value,
            status=RecoveryActionStatus.EXECUTING.value,
            attempt_number=1,
            requires_approval=False,
            idempotency_key=f"link-test:{case.id}:1",
            provider_reference=reference,
        )
        setup.add(action)
        setup.commit()
        case_id = case.id
        amount_at_risk = case.amount_at_risk_minor
    finally:
        setup.close()

    link = payment_link_entity(reference_id=reference, amount=amount_at_risk)
    payment = payment_entity(
        payment_id="pay_plink_corr_001",
        amount=amount_at_risk,
        status="captured",
    )
    payload = build_webhook_payload(
        "payment_link.paid",
        payment=payment,
        payment_link=link,
    )
    raw_body, _, _, headers = signed_request(payload, event_id="evt_plink_corr")
    response = post_webhook(webhook_client, raw_body, headers)
    assert response.status_code == 204

    refreshed = webhook_db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == case_id)
    ).scalar_one()
    assert refreshed.status == RecoveryCaseStatus.RECOVERED.value
    assert webhook_db_session.execute(
        select(func.count()).select_from(RecoveryOutcome).where(RecoveryOutcome.case_id == case_id)
    ).scalar_one() == 1


def test_payment_link_unknown_reference_ignored(
    webhook_client,
    webhook_db_session,
) -> None:
    from app.domain.enums import WebhookProcessingStatus
    from app.models.webhook_event import WebhookEvent

    link = payment_link_entity(reference_id="rq_unknown_ref")
    payment = payment_entity(payment_id="pay_unknown_plink", status="captured")
    payload = build_webhook_payload(
        "payment_link.paid",
        payment=payment,
        payment_link=link,
    )
    raw_body, _, event_id, headers = signed_request(payload)
    response = post_webhook(webhook_client, raw_body, headers)
    assert response.status_code == 204
    event = webhook_db_session.execute(
        select(WebhookEvent).where(WebhookEvent.provider_event_id == event_id)
    ).scalar_one()
    assert event.processing_status == WebhookProcessingStatus.IGNORED.value


def test_payment_link_cross_tenant_no_attribution(
    webhook_client,
    webhook_session_factory,
    webhook_db_session,
) -> None:
    setup = webhook_session_factory()
    reference = "rq_other_tenant"
    try:
        other_org = create_organization(setup)
        customer = create_customer(setup, organization_id=other_org.id)
        case = create_case(
            setup,
            organization_id=other_org.id,
            customer_id=customer.id,
            status=RecoveryCaseStatus.WAITING_FOR_OUTCOME,
        )
        action = RecoveryAction(
            organization_id=other_org.id,
            case_id=case.id,
            action_type=RecoveryActionType.CREATE_PAYMENT_LINK.value,
            status=RecoveryActionStatus.EXECUTING.value,
            attempt_number=1,
            requires_approval=False,
            idempotency_key=f"link-other:{case.id}:1",
            provider_reference=reference,
        )
        setup.add(action)
        setup.commit()
        other_case_id = case.id
    finally:
        setup.close()

    link = payment_link_entity(reference_id=reference)
    payment = payment_entity(payment_id="pay_cross_tenant", status="captured")
    payload = build_webhook_payload(
        "payment_link.paid",
        payment=payment,
        payment_link=link,
    )
    raw_body, _, _, headers = signed_request(payload, event_id="evt_plink_cross_tenant")
    post_webhook(webhook_client, raw_body, headers)

    case = webhook_db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == other_case_id)
    ).scalar_one()
    assert case.status == RecoveryCaseStatus.WAITING_FOR_OUTCOME.value
    outcome_count = webhook_db_session.execute(
        select(func.count())
        .select_from(RecoveryOutcome)
        .where(RecoveryOutcome.case_id == other_case_id)
    ).scalar_one()
    assert outcome_count == 0


def test_terminal_recovered_case_not_rewritten(
    webhook_client,
    webhook_session_factory,
    webhook_db_session,
) -> None:
    setup = webhook_session_factory()
    payment_id = "pay_terminal_001"
    try:
        customer = create_customer(setup, organization_id=DEMO_ORGANIZATION_ID)
        txn = create_transaction(
            setup,
            organization_id=DEMO_ORGANIZATION_ID,
            customer_id=customer.id,
        )
        txn.provider_payment_id = payment_id
        case = create_case(
            setup,
            organization_id=DEMO_ORGANIZATION_ID,
            customer_id=customer.id,
            status=RecoveryCaseStatus.RECOVERED,
        )
        case.transaction_id = txn.id
        setup.commit()
        case_id = case.id
        version_before = case.version
    finally:
        setup.close()

    payment = payment_entity(payment_id=payment_id, status="failed", created_at=1_700_002_000)
    payload = build_webhook_payload("payment.failed", payment=payment)
    raw_body, _, _, headers = signed_request(payload, event_id="evt_terminal_stale_fail")
    post_webhook(webhook_client, raw_body, headers)

    case = webhook_db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == case_id)
    ).scalar_one()
    assert case.status == RecoveryCaseStatus.RECOVERED.value
    assert case.version == version_before


def test_success_while_analyzing_resolves_to_recovered(
    webhook_client,
    webhook_session_factory,
    webhook_db_session,
) -> None:
    setup = webhook_session_factory()
    payment_id = "pay_analyzing_001"
    try:
        customer = create_customer(setup, organization_id=DEMO_ORGANIZATION_ID)
        txn = create_transaction(
            setup,
            organization_id=DEMO_ORGANIZATION_ID,
            customer_id=customer.id,
        )
        txn.provider_payment_id = payment_id
        case = create_case(
            setup,
            organization_id=DEMO_ORGANIZATION_ID,
            customer_id=customer.id,
            status=RecoveryCaseStatus.ANALYZING,
        )
        case.transaction_id = txn.id
        setup.commit()
        case_id = case.id
    finally:
        setup.close()

    payment = payment_entity(payment_id=payment_id, status="captured", created_at=1_700_003_000)
    payload = build_webhook_payload("payment.captured", payment=payment)
    raw_body, _, _, headers = signed_request(payload, event_id="evt_analyzing_cap")
    post_webhook(webhook_client, raw_body, headers)

    case = webhook_db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == case_id)
    ).scalar_one()
    assert case.status == RecoveryCaseStatus.RECOVERED.value


def test_analysis_cannot_overwrite_recovered_after_webhook(
    webhook_client,
    webhook_session_factory,
    webhook_db_session,
) -> None:
    """Verified success committed first; stale analysis completion must not downgrade."""
    setup = webhook_session_factory()
    payment_id = "pay_race_001"
    try:
        customer = create_customer(setup, organization_id=DEMO_ORGANIZATION_ID)
        txn = create_transaction(
            setup,
            organization_id=DEMO_ORGANIZATION_ID,
            customer_id=customer.id,
        )
        txn.provider_payment_id = payment_id
        case = create_case(
            setup,
            organization_id=DEMO_ORGANIZATION_ID,
            customer_id=customer.id,
            status=RecoveryCaseStatus.ANALYZING,
        )
        case.transaction_id = txn.id
        setup.commit()
        case_id = case.id
    finally:
        setup.close()

    payment = payment_entity(payment_id=payment_id, status="captured", created_at=1_700_004_000)
    payload = build_webhook_payload("payment.captured", payment=payment)
    raw_body, _, _, headers = signed_request(payload, event_id="evt_race_cap")
    webhook_response = post_webhook(webhook_client, raw_body, headers)
    assert webhook_response.status_code == 204

    recovered = webhook_db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == case_id)
    ).scalar_one()
    assert recovered.status == RecoveryCaseStatus.RECOVERED.value

    analyze_response = webhook_client.post(
        f"/api/v1/recovery-cases/{case_id}/analyze",
        headers=DEMO_AUTH_HEADERS,
        json={"reason": "MANUAL_ANALYSIS"},
    )
    assert analyze_response.status_code == 409

    final_case = webhook_db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == case_id)
    ).scalar_one()
    assert final_case.status == RecoveryCaseStatus.RECOVERED.value
    assert webhook_db_session.execute(
        select(func.count()).select_from(RecoveryOutcome).where(RecoveryOutcome.case_id == case_id)
    ).scalar_one() == 1
