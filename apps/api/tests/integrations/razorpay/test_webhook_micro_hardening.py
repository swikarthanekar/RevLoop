"""Prompt 14 final micro-hardening regression tests."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.demo.constants import DEMO_ORGANIZATION_ID
from app.domain.enums import RecoveryCaseStatus, WebhookProcessingStatus
from app.models.audit_log import AuditLog
from app.models.recovery_case import RecoveryCase
from app.models.recovery_outcome import RecoveryOutcome
from app.models.transaction import Transaction
from app.models.webhook_event import WebhookEvent
from app.services.provider_events import subscription_pending_source_event_key
from tests.demo.conftest import postgres_available
from tests.integrations.razorpay.conftest import post_webhook
from tests.integrations.razorpay.helpers import (
    build_webhook_payload,
    payment_entity,
    signed_request,
    subscription_entity,
)
from tests.integrations.razorpay.test_webhook_hardening import _seed_subscription
from tests.workflows.helpers import create_case, create_customer, create_transaction

pytestmark = pytest.mark.skipif(
    not postgres_available(),
    reason="PostgreSQL not available",
)


def test_subscription_charged_success_uses_payment_evidence(
    webhook_client,
    webhook_session_factory,
    webhook_db_session,
) -> None:
    sub_id = "sub_charge_evidence"
    cycle_start, cycle_end = 1_700_100_000, 1_700_108_000
    amount = 88800

    setup = webhook_session_factory()
    try:
        _seed_subscription(setup, sub_id=sub_id, amount_minor=amount)
    finally:
        setup.close()

    pending = subscription_entity(
        subscription_id=sub_id,
        status="pending",
        current_start=cycle_start,
        current_end=cycle_end,
    )
    raw_pending, _, _, pending_headers = signed_request(
        build_webhook_payload("subscription.pending", subscription=pending),
        event_id="evt_sub_ev_pending",
    )
    post_webhook(webhook_client, raw_pending, pending_headers)

    payment_id = "pay_sub_evidence_001"
    charged = subscription_entity(
        subscription_id=sub_id,
        status="active",
        current_start=cycle_start,
        current_end=cycle_end,
    )
    payment = payment_entity(payment_id=payment_id, amount=amount, status="captured")
    raw, _, _, headers = signed_request(
        build_webhook_payload(
            "subscription.charged",
            subscription=charged,
            payment=payment,
            created_at=1_700_101_000,
        ),
        event_id="evt_sub_ev_charged",
    )
    assert post_webhook(webhook_client, raw, headers).status_code == 204

    webhook_db_session.expire_all()
    key = subscription_pending_source_event_key(sub_id, f"{cycle_start}:{cycle_end}")
    case = webhook_db_session.execute(
        select(RecoveryCase).where(RecoveryCase.source_event_key == key)
    ).scalar_one()
    assert case.status == RecoveryCaseStatus.RECOVERED.value
    outcome = webhook_db_session.execute(
        select(RecoveryOutcome).where(RecoveryOutcome.case_id == case.id)
    ).scalar_one()
    assert outcome.recovered_payment_id == payment_id
    assert outcome.recovered_amount_minor == amount


def test_subscription_charged_wrong_payment_amount(
    webhook_client,
    webhook_session_factory,
    webhook_db_session,
) -> None:
    sub_id = "sub_charge_wrong_amt"
    cycle_start, cycle_end = 1_700_110_000, 1_700_118_000

    setup = webhook_session_factory()
    try:
        _seed_subscription(setup, sub_id=sub_id, amount_minor=77700)
    finally:
        setup.close()

    pending = subscription_entity(
        subscription_id=sub_id,
        status="pending",
        current_start=cycle_start,
        current_end=cycle_end,
    )
    raw_pending, _, _, pending_headers = signed_request(
        build_webhook_payload("subscription.pending", subscription=pending),
        event_id="evt_sub_wrong_amt_pending",
    )
    post_webhook(webhook_client, raw_pending, pending_headers)

    charged = subscription_entity(
        subscription_id=sub_id,
        status="active",
        current_start=cycle_start,
        current_end=cycle_end,
    )
    payment = payment_entity(payment_id="pay_wrong_amt", amount=1, status="captured")
    raw, _, event_id, headers = signed_request(
        build_webhook_payload(
            "subscription.charged",
            subscription=charged,
            payment=payment,
        ),
        event_id="evt_sub_wrong_amt_charged",
    )
    post_webhook(webhook_client, raw, headers)

    webhook_db_session.expire_all()
    key = subscription_pending_source_event_key(sub_id, f"{cycle_start}:{cycle_end}")
    case = webhook_db_session.execute(
        select(RecoveryCase).where(RecoveryCase.source_event_key == key)
    ).scalar_one()
    assert case.status == RecoveryCaseStatus.DETECTED.value
    assert webhook_db_session.execute(
        select(func.count()).select_from(RecoveryOutcome).where(RecoveryOutcome.case_id == case.id)
    ).scalar_one() == 0
    event = webhook_db_session.execute(
        select(WebhookEvent).where(WebhookEvent.provider_event_id == event_id)
    ).scalar_one()
    assert event.processing_status == WebhookProcessingStatus.IGNORED.value


def test_subscription_charged_wrong_payment_currency(
    webhook_client,
    webhook_session_factory,
    webhook_db_session,
) -> None:
    sub_id = "sub_charge_wrong_cur"
    cycle_start, cycle_end = 1_700_120_000, 1_700_128_000
    amount = 66600

    setup = webhook_session_factory()
    try:
        _seed_subscription(setup, sub_id=sub_id, amount_minor=amount)
    finally:
        setup.close()

    pending = subscription_entity(
        subscription_id=sub_id,
        status="pending",
        current_start=cycle_start,
        current_end=cycle_end,
    )
    raw_pending, _, _, pending_headers = signed_request(
        build_webhook_payload("subscription.pending", subscription=pending),
        event_id="evt_sub_wrong_cur_pending",
    )
    post_webhook(webhook_client, raw_pending, pending_headers)

    charged = subscription_entity(
        subscription_id=sub_id,
        status="active",
        current_start=cycle_start,
        current_end=cycle_end,
    )
    payment = payment_entity(
        payment_id="pay_wrong_cur",
        amount=amount,
        currency="USD",
        status="captured",
    )
    raw, _, event_id, headers = signed_request(
        build_webhook_payload(
            "subscription.charged",
            subscription=charged,
            payment=payment,
        ),
        event_id="evt_sub_wrong_cur_charged",
    )
    post_webhook(webhook_client, raw, headers)

    webhook_db_session.expire_all()
    key = subscription_pending_source_event_key(sub_id, f"{cycle_start}:{cycle_end}")
    case = webhook_db_session.execute(
        select(RecoveryCase).where(RecoveryCase.source_event_key == key)
    ).scalar_one()
    assert case.status == RecoveryCaseStatus.DETECTED.value
    event = webhook_db_session.execute(
        select(WebhookEvent).where(WebhookEvent.provider_event_id == event_id)
    ).scalar_one()
    assert event.processing_status == WebhookProcessingStatus.IGNORED.value


def test_subscription_charged_non_captured_payment_not_recovery(
    webhook_client,
    webhook_session_factory,
    webhook_db_session,
) -> None:
    sub_id = "sub_charge_authorized"
    cycle_start, cycle_end = 1_700_130_000, 1_700_138_000

    setup = webhook_session_factory()
    try:
        _seed_subscription(setup, sub_id=sub_id)
    finally:
        setup.close()

    pending = subscription_entity(
        subscription_id=sub_id,
        status="pending",
        current_start=cycle_start,
        current_end=cycle_end,
    )
    raw_p, _, _, headers_p = signed_request(
        build_webhook_payload("subscription.pending", subscription=pending),
        event_id="evt_sub_auth_pending",
    )
    post_webhook(webhook_client, raw_p, headers_p)

    charged = subscription_entity(
        subscription_id=sub_id,
        status="active",
        current_start=cycle_start,
        current_end=cycle_end,
    )
    payment = payment_entity(payment_id="pay_authorized", amount=99900, status="authorized")
    raw, _, event_id, headers = signed_request(
        build_webhook_payload(
            "subscription.charged",
            subscription=charged,
            payment=payment,
        ),
        event_id="evt_sub_auth_charged",
    )
    post_webhook(webhook_client, raw, headers)

    webhook_db_session.expire_all()
    key = subscription_pending_source_event_key(sub_id, f"{cycle_start}:{cycle_end}")
    case = webhook_db_session.execute(
        select(RecoveryCase).where(RecoveryCase.source_event_key == key)
    ).scalar_one()
    assert case.status == RecoveryCaseStatus.DETECTED.value
    event = webhook_db_session.execute(
        select(WebhookEvent).where(WebhookEvent.provider_event_id == event_id)
    ).scalar_one()
    assert event.processing_status == WebhookProcessingStatus.IGNORED.value
    assert event.processing_error == "INSUFFICIENT_PAYMENT_EVIDENCE"


def test_subscription_charged_missing_payment_entity_returns_400(
    webhook_client,
    webhook_db_session,
) -> None:
    sub_id = "sub_charge_no_payment"
    charged = subscription_entity(subscription_id=sub_id, status="active")
    raw, _, event_id, headers = signed_request(
        build_webhook_payload("subscription.charged", subscription=charged),
        event_id="evt_sub_no_payment",
    )
    before_txn = webhook_db_session.execute(
        select(func.count()).select_from(Transaction)
    ).scalar_one()
    response = post_webhook(webhook_client, raw, headers)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "MALFORMED_WEBHOOK_PAYLOAD"
    after_txn = webhook_db_session.execute(
        select(func.count()).select_from(Transaction)
    ).scalar_one()
    assert after_txn == before_txn
    assert webhook_db_session.execute(
        select(WebhookEvent).where(WebhookEvent.provider_event_id == event_id)
    ).scalar_one_or_none() is None


def test_payment_failed_missing_envelope_created_at_returns_400(
    webhook_client,
    webhook_db_session,
) -> None:
    payment = payment_entity(payment_id="pay_no_event_ts")
    payload = build_webhook_payload("payment.failed", payment=payment, created_at=None)
    raw, _, event_id, headers = signed_request(payload, event_id="evt_no_ts_failed")
    before_txn = webhook_db_session.execute(
        select(func.count()).select_from(Transaction)
    ).scalar_one()
    before_case = webhook_db_session.execute(
        select(func.count()).select_from(RecoveryCase)
    ).scalar_one()
    response = post_webhook(webhook_client, raw, headers)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "MALFORMED_WEBHOOK_PAYLOAD"
    assert webhook_db_session.execute(
        select(func.count()).select_from(Transaction)
    ).scalar_one() == before_txn
    assert webhook_db_session.execute(
        select(func.count()).select_from(RecoveryCase)
    ).scalar_one() == before_case
    assert webhook_db_session.execute(
        select(WebhookEvent).where(WebhookEvent.provider_event_id == event_id)
    ).scalar_one_or_none() is None


def test_payment_captured_missing_envelope_created_at_returns_400(
    webhook_client,
    webhook_session_factory,
    webhook_db_session,
) -> None:
    setup = webhook_session_factory()
    payment_id = "pay_no_ts_cap"
    try:
        customer = create_customer(setup, organization_id=DEMO_ORGANIZATION_ID)
        txn = create_transaction(
            setup,
            organization_id=DEMO_ORGANIZATION_ID,
            customer_id=customer.id,
        )
        txn.provider_payment_id = payment_id
        txn.last_provider_event_at = None
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

    payment = payment_entity(payment_id=payment_id, status="captured")
    payload = build_webhook_payload("payment.captured", payment=payment, created_at=None)
    raw, _, event_id, headers = signed_request(payload, event_id="evt_no_ts_captured")
    response = post_webhook(webhook_client, raw, headers)
    assert response.status_code == 400

    webhook_db_session.expire_all()
    case = webhook_db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == case_id)
    ).scalar_one()
    assert case.status == RecoveryCaseStatus.WAITING_FOR_OUTCOME.value
    assert webhook_db_session.execute(
        select(WebhookEvent).where(WebhookEvent.provider_event_id == event_id)
    ).scalar_one_or_none() is None


def test_terminal_failed_success_records_reconciliation(
    webhook_client,
    webhook_session_factory,
    webhook_db_session,
) -> None:
    setup = webhook_session_factory()
    payment_id = "pay_term_failed_recon"
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
            status=RecoveryCaseStatus.FAILED,
        )
        case.transaction_id = txn.id
        setup.commit()
        case_id = case.id
    finally:
        setup.close()

    payment = payment_entity(payment_id=payment_id, status="captured")
    raw, _, event_id, headers = signed_request(
        build_webhook_payload("payment.captured", payment=payment),
        event_id="evt_term_failed_recon",
    )
    response = post_webhook(webhook_client, raw, headers)
    assert response.status_code == 204

    webhook_db_session.expire_all()
    case = webhook_db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == case_id)
    ).scalar_one()
    assert case.status == RecoveryCaseStatus.FAILED.value
    assert webhook_db_session.execute(
        select(func.count()).select_from(RecoveryOutcome).where(RecoveryOutcome.case_id == case_id)
    ).scalar_one() == 0
    event = webhook_db_session.execute(
        select(WebhookEvent).where(WebhookEvent.provider_event_id == event_id)
    ).scalar_one()
    assert event.processing_status == WebhookProcessingStatus.IGNORED.value
    assert event.processing_error == "TERMINAL_STATE_RECONCILIATION_REQUIRED"
    webhook_db_session.execute(
        select(AuditLog).where(
            AuditLog.case_id == case_id,
            AuditLog.event_type == "TERMINAL_RECONCILIATION_REQUIRED",
        )
    ).scalar_one()


def test_terminal_stopped_success_records_reconciliation(
    webhook_client,
    webhook_session_factory,
    webhook_db_session,
) -> None:
    setup = webhook_session_factory()
    payment_id = "pay_term_stopped_recon"
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
            status=RecoveryCaseStatus.STOPPED,
        )
        case.transaction_id = txn.id
        setup.commit()
        case_id = case.id
    finally:
        setup.close()

    payment = payment_entity(payment_id=payment_id, status="captured")
    raw, _, event_id, headers = signed_request(
        build_webhook_payload("payment.captured", payment=payment),
        event_id="evt_term_stopped_recon",
    )
    response = post_webhook(webhook_client, raw, headers)
    assert response.status_code == 204

    webhook_db_session.expire_all()
    case = webhook_db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == case_id)
    ).scalar_one()
    assert case.status == RecoveryCaseStatus.STOPPED.value
    event = webhook_db_session.execute(
        select(WebhookEvent).where(WebhookEvent.provider_event_id == event_id)
    ).scalar_one()
    assert event.processing_error == "TERMINAL_STATE_RECONCILIATION_REQUIRED"


def test_recovered_replay_no_reconciliation_warning(
    webhook_client,
    webhook_session_factory,
    webhook_db_session,
) -> None:
    setup = webhook_session_factory()
    payment_id = "pay_recovered_replay"
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
    finally:
        setup.close()

    payment = payment_entity(payment_id=payment_id, status="captured")
    payload = build_webhook_payload("payment.captured", payment=payment)
    for suffix in ("a", "b"):
        raw, _, event_id, headers = signed_request(
            payload,
            event_id=f"evt_recovered_replay_{suffix}",
        )
        assert post_webhook(webhook_client, raw, headers).status_code == 204
        event = webhook_db_session.execute(
            select(WebhookEvent).where(WebhookEvent.provider_event_id == event_id)
        ).scalar_one()
        assert event.processing_status == WebhookProcessingStatus.PROCESSED.value
        assert event.processing_error is None

    assert webhook_db_session.execute(
        select(func.count()).select_from(RecoveryOutcome).where(RecoveryOutcome.case_id == case_id)
    ).scalar_one() == 0
    assert webhook_db_session.execute(
        select(func.count())
        .select_from(AuditLog)
        .where(
            AuditLog.case_id == case_id,
            AuditLog.event_type == "TERMINAL_RECONCILIATION_REQUIRED",
        )
    ).scalar_one() == 0
