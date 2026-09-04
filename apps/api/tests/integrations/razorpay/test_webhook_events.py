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
from app.services.provider_events import (
    INSUFFICIENT_FINANCIAL_EVIDENCE,
    payment_failed_source_event_key,
    subscription_pending_source_event_key,
)
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


def test_stale_subscription_charged_does_not_revert_newer_halted_status(
    webhook_client,
    webhook_session_factory,
    webhook_db_session,
) -> None:
    """A `subscription.charged` event delivered out of order, with an
    envelope timestamp older than an already-applied `subscription.halted`,
    must not revert the subscription back to active. If it did, the *next*
    genuinely newer `subscription.pending` for the real new failure would be
    rejected as stale (current_status == CHARGED), and no recovery case would
    ever be created for the real failure."""
    from app.models.subscription import Subscription

    sub_id = "sub_stale_charged_001"
    old_cycle_start = 1_700_000_000
    old_cycle_end = 1_700_000_900
    new_cycle_start = 1_700_002_000
    new_cycle_end = 1_700_002_900

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

    # A genuinely newer halted event is applied first.
    halted = subscription_entity(
        subscription_id=sub_id,
        status="halted",
        current_start=old_cycle_start,
        current_end=old_cycle_end,
    )
    raw_halted, _, _, halted_headers = signed_request(
        build_webhook_payload("subscription.halted", subscription=halted, created_at=1_700_001_000),
        event_id="evt_sub_halted_current",
    )
    post_webhook(webhook_client, raw_halted, halted_headers)

    subscription = webhook_db_session.execute(
        select(Subscription).where(Subscription.provider_subscription_id == sub_id)
    ).scalar_one()
    assert subscription.status == "halted"

    # A stale `subscription.charged` event for an OLDER billing cycle arrives
    # late (out-of-order delivery), with an envelope timestamp older than the
    # halted event already applied.
    stale_charged = subscription_entity(
        subscription_id=sub_id,
        status="active",
        current_start=old_cycle_start,
        current_end=old_cycle_end,
    )
    stale_payment = payment_entity(
        payment_id="pay_stale_charged_001",
        amount=99900,
        status="captured",
    )
    raw_stale, _, _, stale_headers = signed_request(
        build_webhook_payload(
            "subscription.charged",
            subscription=stale_charged,
            payment=stale_payment,
            created_at=1_700_000_500,
        ),
        event_id="evt_sub_stale_charged",
    )
    post_webhook(webhook_client, raw_stale, stale_headers)

    webhook_db_session.expire_all()
    subscription = webhook_db_session.execute(
        select(Subscription).where(Subscription.provider_subscription_id == sub_id)
    ).scalar_one()
    assert subscription.status == "halted"

    # A genuinely newer `subscription.pending` for the real new failure must
    # still be accepted, not rejected as stale, and must create a new case.
    new_pending = subscription_entity(
        subscription_id=sub_id,
        status="pending",
        current_start=new_cycle_start,
        current_end=new_cycle_end,
    )
    raw_pending, _, _, pending_headers = signed_request(
        build_webhook_payload(
            "subscription.pending", subscription=new_pending, created_at=1_700_002_000
        ),
        event_id="evt_sub_new_pending",
    )
    response = post_webhook(webhook_client, raw_pending, pending_headers)
    assert response.status_code == 204

    pending_event = webhook_db_session.execute(
        select(WebhookEvent).where(WebhookEvent.provider_event_id == "evt_sub_new_pending")
    ).scalar_one()
    assert pending_event.processing_status == WebhookProcessingStatus.PROCESSED.value

    key = subscription_pending_source_event_key(
        sub_id, f"{new_cycle_start}:{new_cycle_end}"
    )
    new_case = webhook_db_session.execute(
        select(RecoveryCase).where(RecoveryCase.source_event_key == key)
    ).scalar_one_or_none()
    assert new_case is not None
    assert new_case.status == RecoveryCaseStatus.DETECTED.value


def test_payment_failed_correlation_failure_persists_ignored_event(
    webhook_client,
    webhook_db_session,
) -> None:
    """An uncorrelated payment.failed webhook must not silently vanish. Before
    the fix, the unhandled WebhookCorrelationError rolled back the whole
    transaction -- including the dedup claim insert -- so the event was never
    persisted and every provider retry repeated identical work with zero
    durable trace. It must instead be recorded as IGNORED, matching how the
    subscription handlers already treat the same error class."""
    payment = payment_entity(
        payment_id="pay_uncorrelated_failed_001",
        customer_external_id="no-such-customer-xyz",
    )
    payload = build_webhook_payload("payment.failed", payment=payment)
    raw_body, _, event_id, headers = signed_request(
        payload, event_id="evt_uncorrelated_failed"
    )

    response = post_webhook(webhook_client, raw_body, headers)
    assert response.status_code == 204

    event = webhook_db_session.execute(
        select(WebhookEvent).where(WebhookEvent.provider_event_id == event_id)
    ).scalar_one()
    assert event.processing_status == WebhookProcessingStatus.IGNORED.value
    assert event.processing_error == INSUFFICIENT_FINANCIAL_EVIDENCE

    count = webhook_db_session.execute(
        select(func.count())
        .select_from(Transaction)
        .where(Transaction.provider_payment_id == "pay_uncorrelated_failed_001")
    ).scalar_one()
    assert count == 0


def test_payment_captured_correlation_failure_persists_ignored_event(
    webhook_client,
    webhook_db_session,
) -> None:
    """Same durability guarantee as above, for payment.captured against a
    payment RevLoop has never seen before (so a new Transaction would need to
    be created, which requires customer correlation)."""
    payment = payment_entity(
        payment_id="pay_uncorrelated_captured_001",
        status="captured",
        customer_external_id="no-such-customer-xyz",
    )
    payload = build_webhook_payload("payment.captured", payment=payment)
    raw_body, _, event_id, headers = signed_request(
        payload, event_id="evt_uncorrelated_captured"
    )

    response = post_webhook(webhook_client, raw_body, headers)
    assert response.status_code == 204

    event = webhook_db_session.execute(
        select(WebhookEvent).where(WebhookEvent.provider_event_id == event_id)
    ).scalar_one()
    assert event.processing_status == WebhookProcessingStatus.IGNORED.value
    assert event.processing_error == INSUFFICIENT_FINANCIAL_EVIDENCE

    count = webhook_db_session.execute(
        select(func.count())
        .select_from(Transaction)
        .where(Transaction.provider_payment_id == "pay_uncorrelated_captured_001")
    ).scalar_one()
    assert count == 0


def test_unknown_event_persisted_and_ignored(webhook_client, webhook_db_session) -> None:
    payload = {"event": "invoice.paid", "created_at": 1_700_000_000, "payload": {}}
    raw_body, _, event_id, headers = signed_request(payload)
    response = post_webhook(webhook_client, raw_body, headers)
    assert response.status_code == 204
    event = webhook_db_session.execute(
        select(WebhookEvent).where(WebhookEvent.provider_event_id == event_id)
    ).scalar_one()
    assert event.processing_status == WebhookProcessingStatus.IGNORED.value
