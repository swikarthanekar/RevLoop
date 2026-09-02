"""Razorpay webhook idempotency and event processing tests."""

from __future__ import annotations

import threading

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.deps import get_db
from app.demo.constants import DEMO_ORGANIZATION_ID
from app.domain.enums import RecoveryCaseStatus, RecoveryOutcomeType, WebhookProcessingStatus
from app.main import create_app
from app.models.recovery_case import RecoveryCase
from app.models.recovery_outcome import RecoveryOutcome
from app.models.transaction import Transaction
from app.models.webhook_event import WebhookEvent
from app.repositories.webhook_events import PROVIDER_RAZORPAY
from app.services.provider_events import payment_failed_source_event_key
from tests.integrations.razorpay.conftest import WEBHOOK_PATH, post_webhook
from tests.integrations.razorpay.helpers import (
    build_webhook_payload,
    payment_entity,
    signed_request,
    subscription_entity,
)
from tests.workflows.helpers import create_case, create_customer, create_transaction


def test_sequential_duplicate_event_id(webhook_client, webhook_db_session) -> None:
    payment = payment_entity(payment_id="pay_dup_seq_001")
    payload = build_webhook_payload("payment.failed", payment=payment)
    event_id = "evt_dup_seq_001"
    raw_body, _, _, headers = signed_request(payload, event_id=event_id)
    first = post_webhook(webhook_client, raw_body, headers)
    second = post_webhook(webhook_client, raw_body, headers)
    assert first.status_code == 204
    assert second.status_code == 204
    count = webhook_db_session.execute(
        select(func.count())
        .select_from(WebhookEvent)
        .where(WebhookEvent.provider_event_id == event_id)
    ).scalar_one()
    assert count == 1


def test_concurrent_duplicate_event_id(
    webhook_seeded_database,
    webhook_test_settings,
) -> None:
    payment = payment_entity(payment_id="pay_dup_conc_001")
    payload = build_webhook_payload("payment.failed", payment=payment)
    event_id = "evt_dup_conc_001"
    raw_body, _, _, headers = signed_request(payload, event_id=event_id)
    results: list[int] = []
    barrier = threading.Barrier(2)

    def worker() -> None:
        app = create_app()

        def override_get_db():
            bind = webhook_seeded_database
            session = sessionmaker(bind=bind, autoflush=False, autocommit=False)()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_settings] = lambda: webhook_test_settings
        from fastapi.testclient import TestClient

        client = TestClient(app, raise_server_exceptions=False)
        barrier.wait(timeout=5)
        response = client.post(WEBHOOK_PATH, content=raw_body, headers=headers)
        results.append(response.status_code)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert sorted(results) == [204, 204]
    verify_session = sessionmaker(bind=webhook_seeded_database)()
    try:
        event_count = verify_session.execute(
            select(func.count())
            .select_from(WebhookEvent)
            .where(WebhookEvent.provider_event_id == event_id)
        ).scalar_one()
        case_count = verify_session.execute(
            select(func.count())
            .select_from(RecoveryCase)
            .where(
                RecoveryCase.source_event_key
                == payment_failed_source_event_key("pay_dup_conc_001")
            )
        ).scalar_one()
        assert event_count == 1
        assert case_count == 1
    finally:
        verify_session.close()


def test_payment_failed_creates_detected_case(webhook_client, webhook_db_session) -> None:
    payment_id = "pay_failed_create_001"
    payment = payment_entity(payment_id=payment_id, amount=250000)
    payload = build_webhook_payload("payment.failed", payment=payment, created_at=1_700_000_100)
    raw_body, _, _, headers = signed_request(payload, event_id="evt_failed_create_001")
    response = post_webhook(webhook_client, raw_body, headers)
    assert response.status_code == 204

    txn = webhook_db_session.execute(
        select(Transaction).where(Transaction.provider_payment_id == payment_id)
    ).scalar_one()
    assert txn.amount_minor == 250000
    assert txn.currency == "INR"
    assert txn.organization_id == DEMO_ORGANIZATION_ID

    case = webhook_db_session.execute(
        select(RecoveryCase).where(
            RecoveryCase.source_event_key == payment_failed_source_event_key(payment_id)
        )
    ).scalar_one()
    assert case.status == RecoveryCaseStatus.DETECTED.value
    assert case.transaction_id == txn.id
    assert case.current_analysis_run_id is None


def test_repeated_payment_failed_no_duplicate_case(
    webhook_client,
    webhook_db_session,
) -> None:
    payment_id = "pay_failed_repeat_001"
    payment = payment_entity(payment_id=payment_id)
    payload = build_webhook_payload("payment.failed", payment=payment)
    raw_body, _, _, headers = signed_request(payload, event_id="evt_failed_repeat_001")
    post_webhook(webhook_client, raw_body, headers)
    raw_body2, _, _, headers2 = signed_request(payload, event_id="evt_failed_repeat_002")
    post_webhook(webhook_client, raw_body2, headers2)
    count = webhook_db_session.execute(
        select(func.count())
        .select_from(RecoveryCase)
        .where(
            RecoveryCase.source_event_key == payment_failed_source_event_key(payment_id)
        )
    ).scalar_one()
    assert count == 1


def test_payment_captured_resolves_case(
    webhook_client,
    webhook_session_factory,
    webhook_db_session,
) -> None:
    setup = webhook_session_factory()
    try:
        customer = create_customer(setup, organization_id=DEMO_ORGANIZATION_ID)
        payment_id = "pay_capture_resolve_001"
        txn = create_transaction(
            setup,
            organization_id=DEMO_ORGANIZATION_ID,
            customer_id=customer.id,
        )
        txn.provider_payment_id = payment_id
        txn.status = "failed"
        case = create_case(
            setup,
            organization_id=DEMO_ORGANIZATION_ID,
            customer_id=customer.id,
            status=RecoveryCaseStatus.RECOMMENDED,
        )
        case.transaction_id = txn.id
        setup.commit()
        case_id = case.id
    finally:
        setup.close()

    payment = payment_entity(
        payment_id=payment_id,
        status="captured",
        created_at=1_700_000_200,
    )
    payload = build_webhook_payload("payment.captured", payment=payment, created_at=1_700_000_200)
    raw_body, _, _, headers = signed_request(payload, event_id="evt_capture_resolve_001")
    response = post_webhook(webhook_client, raw_body, headers)
    assert response.status_code == 204

    refreshed = webhook_db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == case_id)
    ).scalar_one()
    assert refreshed.status == RecoveryCaseStatus.RECOVERED.value
    outcomes = webhook_db_session.execute(
        select(RecoveryOutcome).where(RecoveryOutcome.case_id == case_id)
    ).scalars().all()
    assert len(outcomes) == 1
    assert outcomes[0].outcome == RecoveryOutcomeType.RECOVERED.value


def test_repeated_payment_captured_does_not_duplicate_outcome(
    webhook_client,
    webhook_session_factory,
    webhook_db_session,
) -> None:
    setup = webhook_session_factory()
    payment_id = "pay_capture_dup_001"
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
            status=RecoveryCaseStatus.DETECTED,
        )
        case.transaction_id = txn.id
        setup.commit()
        case_id = case.id
    finally:
        setup.close()

    payment = payment_entity(payment_id=payment_id, status="captured", created_at=1_700_000_300)
    payload = build_webhook_payload("payment.captured", payment=payment)
    for event_suffix in ("a", "b"):
        raw_body, _, _, headers = signed_request(
            payload,
            event_id=f"evt_capture_dup_{event_suffix}",
        )
        post_webhook(webhook_client, raw_body, headers)

    count = webhook_db_session.execute(
        select(func.count()).select_from(RecoveryOutcome).where(RecoveryOutcome.case_id == case_id)
    ).scalar_one()
    assert count == 1


def test_captured_before_old_failed_preserves_success(
    webhook_client,
    webhook_session_factory,
    webhook_db_session,
) -> None:
    setup = webhook_session_factory()
    payment_id = "pay_order_001"
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
            status=RecoveryCaseStatus.WAITING_FOR_OUTCOME,
        )
        case.transaction_id = txn.id
        setup.commit()
        case_id = case.id
    finally:
        setup.close()

    captured = payment_entity(payment_id=payment_id, status="captured", created_at=1_700_000_500)
    cap_payload = build_webhook_payload(
        "payment.captured", payment=captured, created_at=1_700_000_500
    )
    raw_cap, _, _, cap_headers = signed_request(cap_payload, event_id="evt_order_cap")
    post_webhook(webhook_client, raw_cap, cap_headers)

    failed = payment_entity(payment_id=payment_id, status="failed", created_at=1_700_000_100)
    fail_payload = build_webhook_payload(
        "payment.failed", payment=failed, created_at=1_700_000_100
    )
    raw_fail, _, _, fail_headers = signed_request(fail_payload, event_id="evt_order_fail")
    post_webhook(webhook_client, raw_fail, fail_headers)

    txn = webhook_db_session.execute(
        select(Transaction).where(Transaction.provider_payment_id == payment_id)
    ).scalar_one()
    assert txn.status == "captured"

    case = webhook_db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == case_id)
    ).scalar_one()
    assert case.status == RecoveryCaseStatus.RECOVERED.value

    stale = webhook_db_session.execute(
        select(WebhookEvent).where(WebhookEvent.provider_event_id == "evt_order_fail")
    ).scalar_one()
    assert stale.processing_status == WebhookProcessingStatus.IGNORED.value


def test_subscription_charged_before_old_pending(
    webhook_client,
    webhook_session_factory,
    webhook_db_session,
) -> None:
    from app.models.subscription import Subscription

    sub_id = "sub_order_001"
    cycle_start = 1_700_000_800
    cycle_end = 1_700_001_600
    setup = webhook_session_factory()
    try:
        customer = create_customer(setup, organization_id=DEMO_ORGANIZATION_ID)
        setup.add(
            Subscription(
                organization_id=DEMO_ORGANIZATION_ID,
                customer_id=customer.id,
                provider=PROVIDER_RAZORPAY,
                provider_subscription_id=sub_id,
                amount_minor=99900,
                currency="INR",
                status="pending",
                retry_count=0,
                is_synthetic=False,
            )
        )
        setup.commit()
    finally:
        setup.close()

    charged = subscription_entity(
        subscription_id=sub_id,
        status="active",
        created_at=1_700_000_100,
        current_start=cycle_start,
        current_end=cycle_end,
    )
    charge_payment = payment_entity(
        payment_id="pay_sub_order_charged",
        amount=99900,
        status="captured",
    )
    charged_payload = build_webhook_payload(
        "subscription.charged",
        subscription=charged,
        payment=charge_payment,
        created_at=1_700_001_000,
    )
    raw_charged, _, _, charged_headers = signed_request(
        charged_payload, event_id="evt_sub_charged"
    )
    post_webhook(webhook_client, raw_charged, charged_headers)

    pending = subscription_entity(
        subscription_id=sub_id,
        status="pending",
        created_at=1_700_000_500,
        current_start=cycle_start,
        current_end=cycle_end,
    )
    pending_payload = build_webhook_payload(
        "subscription.pending", subscription=pending, created_at=1_700_000_500
    )
    raw_pending, _, _, pending_headers = signed_request(
        pending_payload, event_id="evt_sub_pending_old"
    )
    post_webhook(webhook_client, raw_pending, pending_headers)

    stale = webhook_db_session.execute(
        select(WebhookEvent).where(WebhookEvent.provider_event_id == "evt_sub_pending_old")
    ).scalar_one()
    assert stale.processing_status == WebhookProcessingStatus.IGNORED.value


def test_unknown_event_persisted_and_ignored(webhook_client, webhook_db_session) -> None:
    payload = {"event": "invoice.paid", "created_at": 1_700_000_000, "payload": {}}
    raw_body, _, event_id, headers = signed_request(payload)
    response = post_webhook(webhook_client, raw_body, headers)
    assert response.status_code == 204
    event = webhook_db_session.execute(
        select(WebhookEvent).where(WebhookEvent.provider_event_id == event_id)
    ).scalar_one()
    assert event.processing_status == WebhookProcessingStatus.IGNORED.value
