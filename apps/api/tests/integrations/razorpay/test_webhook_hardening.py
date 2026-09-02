"""Prompt 14 acceptance-hardening regression tests."""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.deps import get_db
from app.demo.constants import DEMO_ORGANIZATION_ID
from app.domain.enums import (
    RecoveryActionStatus,
    RecoveryActionType,
    RecoveryCaseStatus,
    WebhookProcessingStatus,
)
from app.main import create_app
from app.models.recovery_action import RecoveryAction
from app.models.recovery_case import RecoveryCase
from app.models.recovery_outcome import RecoveryOutcome
from app.models.subscription import Subscription
from app.models.transaction import Transaction
from app.models.webhook_event import WebhookEvent
from app.repositories.webhook_events import PROVIDER_RAZORPAY
from app.services.provider_events import (
    ProviderEventService,
    subscription_pending_source_event_key,
)
from app.workflows.exceptions import WorkflowError
from tests.demo.conftest import postgres_available
from tests.integrations.razorpay.conftest import post_webhook
from tests.integrations.razorpay.helpers import (
    WEBHOOK_SECRET,
    build_webhook_payload,
    payment_entity,
    payment_link_entity,
    signed_request,
    subscription_entity,
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
def blank_secret_client(
    webhook_seeded_database,
    webhook_test_settings,
) -> Generator[TestClient, None, None]:
    app = create_app()
    blank_settings = webhook_test_settings.model_copy(
        update={"razorpay_webhook_secret": SecretStr("   ")},
    )

    def override_get_db() -> Generator[Session, None, None]:
        session = sessionmaker(bind=webhook_seeded_database, autoflush=False, autocommit=False)()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: blank_settings
    client = TestClient(app, raise_server_exceptions=False)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


def test_blank_webhook_secret_rejected(blank_secret_client) -> None:
    payment = payment_entity(payment_id="pay_blank_secret")
    payload = build_webhook_payload("payment.failed", payment=payment)
    raw_body, _, _, headers = signed_request(payload, secret=WEBHOOK_SECRET)
    response = post_webhook(blank_secret_client, raw_body, headers)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "WEBHOOK_CONFIGURATION_ERROR"


def test_db_unavailable_returns_503_safe_body(webhook_client, webhook_db_session) -> None:
    payment = payment_entity(payment_id="pay_db_down_001")
    payload = build_webhook_payload("payment.failed", payment=payment)
    raw_body, _, event_id, headers = signed_request(payload, event_id="evt_db_down_001")

    def raise_operational(*args, **kwargs):
        raise OperationalError("connection failed", {}, Exception("connection refused"))

    before_txn = webhook_db_session.execute(
        select(func.count()).select_from(Transaction)
    ).scalar_one()

    with patch.object(
        ProviderEventService,
        "ingest_razorpay_webhook",
        side_effect=OperationalError("connection failed", {}, Exception("connection refused")),
    ):
        response = post_webhook(webhook_client, raw_body, headers)

    assert response.status_code == 503
    body = response.text
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
    forbidden_tokens = (
        "postgresql",
        "password",
        "revloop@",
        "traceback",
        "SELECT",
        "connection refused",
    )
    for forbidden in forbidden_tokens:
        assert forbidden.lower() not in body.lower()

    after_txn = webhook_db_session.execute(
        select(func.count()).select_from(Transaction)
    ).scalar_one()
    assert after_txn == before_txn


def test_retry_after_claim_failure_same_event_id(
    webhook_client,
    webhook_db_session,
) -> None:
    payment_id = "pay_retry_claim_001"
    payment = payment_entity(payment_id=payment_id)
    payload = build_webhook_payload("payment.failed", payment=payment)
    event_id = "evt_retry_claim_001"
    raw_body, _, _, headers = signed_request(payload, event_id=event_id)

    original = ProviderEventService._create_payment_failure_case_if_absent
    calls = {"count": 0}

    def flaky_create(self, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("simulated downstream failure")
        return original(self, **kwargs)

    with patch.object(ProviderEventService, "_create_payment_failure_case_if_absent", flaky_create):
        first = post_webhook(webhook_client, raw_body, headers)
    assert first.status_code == 500

    second = post_webhook(webhook_client, raw_body, headers)
    assert second.status_code == 204

    webhook_count = webhook_db_session.execute(
        select(func.count())
        .select_from(WebhookEvent)
        .where(WebhookEvent.provider_event_id == event_id)
    ).scalar_one()
    txn_count = webhook_db_session.execute(
        select(func.count())
        .select_from(Transaction)
        .where(Transaction.provider_payment_id == payment_id)
    ).scalar_one()
    case_count = webhook_db_session.execute(
        select(func.count()).select_from(RecoveryCase).where(
            RecoveryCase.source_event_key == f"razorpay:payment_failed:{payment_id}"
        )
    ).scalar_one()
    assert webhook_count == 1
    assert txn_count == 1
    assert case_count == 1


def test_retry_after_workflow_commit_before_mark_processed(
    webhook_client,
    webhook_session_factory,
    webhook_db_session,
) -> None:
    setup = webhook_session_factory()
    payment_id = "pay_retry_sm_001"
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

    payment = payment_entity(payment_id=payment_id, status="captured")
    payload = build_webhook_payload("payment.captured", payment=payment)
    event_id = "evt_retry_sm_001"
    raw_body, _, _, headers = signed_request(payload, event_id=event_id)

    from app.repositories.webhook_events import WebhookEventRepository

    original_mark = WebhookEventRepository.mark_processed
    calls = {"count": 0}

    def flaky_mark(self, session, *, event, processed_at):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("simulated post-commit failure")
        return original_mark(self, session, event=event, processed_at=processed_at)

    with patch.object(WebhookEventRepository, "mark_processed", flaky_mark):
        first = post_webhook(webhook_client, raw_body, headers)
    assert first.status_code == 500

    second = post_webhook(webhook_client, raw_body, headers)
    assert second.status_code == 204

    case = webhook_db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == case_id)
    ).scalar_one()
    assert case.status == RecoveryCaseStatus.RECOVERED.value
    outcome_count = webhook_db_session.execute(
        select(func.count()).select_from(RecoveryOutcome).where(RecoveryOutcome.case_id == case_id)
    ).scalar_one()
    assert outcome_count == 1
    event = webhook_db_session.execute(
        select(WebhookEvent).where(WebhookEvent.provider_event_id == event_id)
    ).scalar_one()
    assert event.processing_status == WebhookProcessingStatus.PROCESSED.value


def _seed_subscription(
    session: Session,
    *,
    sub_id: str,
    amount_minor: int = 99900,
    currency: str = "INR",
) -> None:
    customer = create_customer(session, organization_id=DEMO_ORGANIZATION_ID)
    session.add(
        Subscription(
            organization_id=DEMO_ORGANIZATION_ID,
            customer_id=customer.id,
            provider=PROVIDER_RAZORPAY,
            provider_subscription_id=sub_id,
            amount_minor=amount_minor,
            currency=currency,
            status="pending",
            retry_count=0,
            is_synthetic=False,
        )
    )
    session.commit()


def test_subscription_pending_no_money_in_notes(
    webhook_client,
    webhook_session_factory,
    webhook_db_session,
) -> None:
    sub_id = "sub_no_money_notes"
    setup = webhook_session_factory()
    try:
        _seed_subscription(setup, sub_id=sub_id, amount_minor=88800)
    finally:
        setup.close()

    sub = subscription_entity(
        subscription_id=sub_id,
        status="pending",
        notes={"foo": "bar"},
        current_start=1_700_010_000,
        current_end=1_700_018_000,
    )
    payload = build_webhook_payload("subscription.pending", subscription=sub)
    raw_body, _, _, headers = signed_request(payload, event_id="evt_sub_no_notes_money")
    response = post_webhook(webhook_client, raw_body, headers)
    assert response.status_code == 204

    case = webhook_db_session.execute(
        select(RecoveryCase).where(
            RecoveryCase.source_event_key
            == subscription_pending_source_event_key(sub_id, "1700010000:1700018000")
        )
    ).scalar_one()
    assert case.amount_at_risk_minor == 88800
    assert case.currency == "INR"


def test_subscription_notes_cannot_override_trusted_money(
    webhook_client,
    webhook_session_factory,
    webhook_db_session,
) -> None:
    sub_id = "sub_notes_override"
    setup = webhook_session_factory()
    try:
        _seed_subscription(setup, sub_id=sub_id, amount_minor=77700, currency="INR")
    finally:
        setup.close()

    sub = subscription_entity(
        subscription_id=sub_id,
        status="pending",
        notes={"amount_minor": 999999999, "currency": "XYZ"},
        current_start=1_700_020_000,
        current_end=1_700_028_000,
    )
    payload = build_webhook_payload("subscription.pending", subscription=sub)
    raw_body, _, _, headers = signed_request(payload, event_id="evt_sub_notes_override")
    post_webhook(webhook_client, raw_body, headers)

    case = webhook_db_session.execute(
        select(RecoveryCase).where(
            RecoveryCase.source_event_key
            == subscription_pending_source_event_key(sub_id, "1700020000:1700028000")
        )
    ).scalar_one()
    assert case.amount_at_risk_minor == 77700
    assert case.currency == "INR"


def test_subscription_unknown_local_record_ignored(
    webhook_client,
    webhook_db_session,
) -> None:
    sub = subscription_entity(
        subscription_id="sub_no_local_record",
        status="pending",
        notes={"foo": "bar"},
        current_start=1_700_030_000,
        current_end=1_700_038_000,
    )
    payload = build_webhook_payload("subscription.pending", subscription=sub)
    raw_body, _, event_id, headers = signed_request(payload, event_id="evt_sub_no_local")
    post_webhook(webhook_client, raw_body, headers)

    case_count = webhook_db_session.execute(
        select(func.count()).select_from(RecoveryCase).where(
            RecoveryCase.source_event_key.like("razorpay:subscription_pending:sub_no_local_record:%")
        )
    ).scalar_one()
    assert case_count == 0
    event = webhook_db_session.execute(
        select(WebhookEvent).where(WebhookEvent.provider_event_id == event_id)
    ).scalar_one()
    assert event.processing_status == WebhookProcessingStatus.IGNORED.value


def test_subscription_cross_cycle_charged_resolves_only_matching_cycle(
    webhook_client,
    webhook_session_factory,
    webhook_db_session,
) -> None:
    sub_id = "sub_cross_cycle"
    cycle_a_start, cycle_a_end = 1_700_040_000, 1_700_048_000
    cycle_b_start, cycle_b_end = 1_700_050_000, 1_700_058_000

    setup = webhook_session_factory()
    try:
        _seed_subscription(setup, sub_id=sub_id)
    finally:
        setup.close()

    pending_a = subscription_entity(
        subscription_id=sub_id,
        status="pending",
        current_start=cycle_a_start,
        current_end=cycle_a_end,
        created_at=1_700_040_100,
    )
    raw_a, _, _, headers_a = signed_request(
        build_webhook_payload(
            "subscription.pending",
            subscription=pending_a,
            created_at=1_700_040_100,
        ),
        event_id="evt_sub_cycle_a_pending",
    )
    post_webhook(webhook_client, raw_a, headers_a)

    pending_b = subscription_entity(
        subscription_id=sub_id,
        status="pending",
        current_start=cycle_b_start,
        current_end=cycle_b_end,
        created_at=1_700_050_100,
    )
    raw_b, _, _, headers_b = signed_request(
        build_webhook_payload(
            "subscription.pending",
            subscription=pending_b,
            created_at=1_700_050_100,
        ),
        event_id="evt_sub_cycle_b_pending",
    )
    post_webhook(webhook_client, raw_b, headers_b)

    key_a = subscription_pending_source_event_key(sub_id, f"{cycle_a_start}:{cycle_a_end}")
    key_b = subscription_pending_source_event_key(sub_id, f"{cycle_b_start}:{cycle_b_end}")
    case_a = webhook_db_session.execute(
        select(RecoveryCase).where(RecoveryCase.source_event_key == key_a)
    ).scalar_one()
    case_b = webhook_db_session.execute(
        select(RecoveryCase).where(RecoveryCase.source_event_key == key_b)
    ).scalar_one()

    charged_b = subscription_entity(
        subscription_id=sub_id,
        status="active",
        current_start=cycle_b_start,
        current_end=cycle_b_end,
        created_at=1_700_040_000,
    )
    charge_payment = payment_entity(
        payment_id="pay_sub_cycle_b",
        amount=99900,
        status="captured",
    )
    raw_charged, _, _, charged_headers = signed_request(
        build_webhook_payload(
            "subscription.charged",
            subscription=charged_b,
            payment=charge_payment,
            created_at=1_700_051_000,
        ),
        event_id="evt_sub_cycle_b_charged",
    )
    post_webhook(webhook_client, raw_charged, charged_headers)

    webhook_db_session.expire_all()
    refreshed_a = webhook_db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == case_a.id)
    ).scalar_one()
    refreshed_b = webhook_db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == case_b.id)
    ).scalar_one()
    assert refreshed_a.status == RecoveryCaseStatus.DETECTED.value
    assert refreshed_b.status == RecoveryCaseStatus.RECOVERED.value
    assert webhook_db_session.execute(
        select(func.count())
        .select_from(RecoveryOutcome)
        .where(RecoveryOutcome.case_id == case_b.id)
    ).scalar_one() == 1
    assert webhook_db_session.execute(
        select(func.count())
        .select_from(RecoveryOutcome)
        .where(RecoveryOutcome.case_id == case_a.id)
    ).scalar_one() == 0


def test_duplicate_provider_reference_tenant_scoped(
    webhook_client,
    webhook_session_factory,
    webhook_db_session,
) -> None:
    setup = webhook_session_factory()
    reference = "rq_dup_ref_tenant"
    try:
        other_org = create_organization(setup)
        other_customer = create_customer(setup, organization_id=other_org.id)
        other_case = create_case(
            setup,
            organization_id=other_org.id,
            customer_id=other_customer.id,
            status=RecoveryCaseStatus.WAITING_FOR_OUTCOME,
        )
        setup.add(
            RecoveryAction(
                organization_id=other_org.id,
                case_id=other_case.id,
                action_type=RecoveryActionType.CREATE_PAYMENT_LINK.value,
                status=RecoveryActionStatus.EXECUTING.value,
                attempt_number=1,
                requires_approval=False,
                idempotency_key=f"dup-other:{other_case.id}:1",
                provider_reference=reference,
            )
        )

        demo_customer = create_customer(setup, organization_id=DEMO_ORGANIZATION_ID)
        demo_case = create_case(
            setup,
            organization_id=DEMO_ORGANIZATION_ID,
            customer_id=demo_customer.id,
            status=RecoveryCaseStatus.WAITING_FOR_OUTCOME,
        )
        setup.add(
            RecoveryAction(
                organization_id=DEMO_ORGANIZATION_ID,
                case_id=demo_case.id,
                action_type=RecoveryActionType.CREATE_PAYMENT_LINK.value,
                status=RecoveryActionStatus.EXECUTING.value,
                attempt_number=1,
                requires_approval=False,
                idempotency_key=f"dup-demo:{demo_case.id}:1",
                provider_reference=reference,
            )
        )
        setup.commit()
        demo_case_id = demo_case.id
        other_case_id = other_case.id
        amount = demo_case.amount_at_risk_minor
    finally:
        setup.close()

    link = payment_link_entity(reference_id=reference, amount=amount)
    payment = payment_entity(payment_id="pay_dup_ref", amount=amount, status="captured")
    payload = build_webhook_payload("payment_link.paid", payment=payment, payment_link=link)
    raw_body, _, _, headers = signed_request(payload, event_id="evt_dup_ref_tenant")
    response = post_webhook(webhook_client, raw_body, headers)
    assert response.status_code == 204

    demo = webhook_db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == demo_case_id)
    ).scalar_one()
    other = webhook_db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == other_case_id)
    ).scalar_one()
    assert demo.status == RecoveryCaseStatus.RECOVERED.value
    assert other.status == RecoveryCaseStatus.WAITING_FOR_OUTCOME.value


def test_payment_captured_wrong_amount_no_recovery(
    webhook_client,
    webhook_session_factory,
    webhook_db_session,
) -> None:
    setup = webhook_session_factory()
    payment_id = "pay_wrong_amount"
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

    payment = payment_entity(payment_id=payment_id, amount=1, status="captured")
    payload = build_webhook_payload("payment.captured", payment=payment)
    raw_body, _, event_id, headers = signed_request(payload, event_id="evt_wrong_amount")
    post_webhook(webhook_client, raw_body, headers)

    case = webhook_db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == case_id)
    ).scalar_one()
    assert case.status == RecoveryCaseStatus.WAITING_FOR_OUTCOME.value
    assert webhook_db_session.execute(
        select(func.count()).select_from(RecoveryOutcome).where(RecoveryOutcome.case_id == case_id)
    ).scalar_one() == 0
    event = webhook_db_session.execute(
        select(WebhookEvent).where(WebhookEvent.provider_event_id == event_id)
    ).scalar_one()
    assert event.processing_status == WebhookProcessingStatus.IGNORED.value


def test_payment_captured_wrong_currency_no_recovery(
    webhook_client,
    webhook_session_factory,
    webhook_db_session,
) -> None:
    setup = webhook_session_factory()
    payment_id = "pay_wrong_currency"
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

    payment = payment_entity(
        payment_id=payment_id,
        amount=499900,
        currency="USD",
        status="captured",
    )
    payload = build_webhook_payload("payment.captured", payment=payment)
    raw_body, _, event_id, headers = signed_request(payload, event_id="evt_wrong_currency")
    post_webhook(webhook_client, raw_body, headers)

    case = webhook_db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == case_id)
    ).scalar_one()
    assert case.status == RecoveryCaseStatus.WAITING_FOR_OUTCOME.value
    event = webhook_db_session.execute(
        select(WebhookEvent).where(WebhookEvent.provider_event_id == event_id)
    ).scalar_one()
    assert event.processing_status == WebhookProcessingStatus.IGNORED.value


def test_payment_link_wrong_amount_no_recovery(
    webhook_client,
    webhook_session_factory,
    webhook_db_session,
) -> None:
    setup = webhook_session_factory()
    reference = "rq_wrong_plink_amt"
    try:
        customer = create_customer(setup, organization_id=DEMO_ORGANIZATION_ID)
        case = create_case(
            setup,
            organization_id=DEMO_ORGANIZATION_ID,
            customer_id=customer.id,
            status=RecoveryCaseStatus.WAITING_FOR_OUTCOME,
        )
        setup.add(
            RecoveryAction(
                organization_id=DEMO_ORGANIZATION_ID,
                case_id=case.id,
                action_type=RecoveryActionType.CREATE_PAYMENT_LINK.value,
                status=RecoveryActionStatus.EXECUTING.value,
                attempt_number=1,
                requires_approval=False,
                idempotency_key=f"plink-amt:{case.id}:1",
                provider_reference=reference,
            )
        )
        setup.commit()
        case_id = case.id
    finally:
        setup.close()

    link = payment_link_entity(reference_id=reference)
    payment = payment_entity(payment_id="pay_plink_wrong_amt", amount=1, status="captured")
    payload = build_webhook_payload("payment_link.paid", payment=payment, payment_link=link)
    raw_body, _, event_id, headers = signed_request(payload, event_id="evt_plink_wrong_amt")
    post_webhook(webhook_client, raw_body, headers)

    case = webhook_db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == case_id)
    ).scalar_one()
    assert case.status == RecoveryCaseStatus.WAITING_FOR_OUTCOME.value
    event = webhook_db_session.execute(
        select(WebhookEvent).where(WebhookEvent.provider_event_id == event_id)
    ).scalar_one()
    assert event.processing_status == WebhookProcessingStatus.IGNORED.value


def test_payment_link_wrong_currency_no_recovery(
    webhook_client,
    webhook_session_factory,
    webhook_db_session,
) -> None:
    setup = webhook_session_factory()
    reference = "rq_wrong_plink_cur"
    try:
        customer = create_customer(setup, organization_id=DEMO_ORGANIZATION_ID)
        case = create_case(
            setup,
            organization_id=DEMO_ORGANIZATION_ID,
            customer_id=customer.id,
            status=RecoveryCaseStatus.WAITING_FOR_OUTCOME,
        )
        setup.add(
            RecoveryAction(
                organization_id=DEMO_ORGANIZATION_ID,
                case_id=case.id,
                action_type=RecoveryActionType.CREATE_PAYMENT_LINK.value,
                status=RecoveryActionStatus.EXECUTING.value,
                attempt_number=1,
                requires_approval=False,
                idempotency_key=f"plink-cur:{case.id}:1",
                provider_reference=reference,
            )
        )
        setup.commit()
        case_id = case.id
        amount = case.amount_at_risk_minor
    finally:
        setup.close()

    link = payment_link_entity(reference_id=reference, amount=amount)
    payment = payment_entity(
        payment_id="pay_plink_wrong_cur",
        amount=amount,
        currency="USD",
        status="captured",
    )
    payload = build_webhook_payload("payment_link.paid", payment=payment, payment_link=link)
    raw_body, _, event_id, headers = signed_request(payload, event_id="evt_plink_wrong_cur")
    post_webhook(webhook_client, raw_body, headers)

    case = webhook_db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == case_id)
    ).scalar_one()
    assert case.status == RecoveryCaseStatus.WAITING_FOR_OUTCOME.value
    event = webhook_db_session.execute(
        select(WebhookEvent).where(WebhookEvent.provider_event_id == event_id)
    ).scalar_one()
    assert event.processing_status == WebhookProcessingStatus.IGNORED.value


def test_forced_payment_verified_failure_no_partial_outcome(
    webhook_client,
    webhook_session_factory,
    webhook_db_session,
) -> None:
    setup = webhook_session_factory()
    payment_id = "pay_force_wf_fail"
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

    payment = payment_entity(payment_id=payment_id, status="captured")
    payload = build_webhook_payload("payment.captured", payment=payment)
    event_id = "evt_force_wf_fail"
    raw_body, _, _, headers = signed_request(payload, event_id=event_id)

    with patch(
        "app.services.provider_events.RecoveryCaseStateMachine.resolve_verified_success",
        side_effect=WorkflowError("forced failure"),
    ):
        response = post_webhook(webhook_client, raw_body, headers)
    assert response.status_code == 500

    case = webhook_db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == case_id)
    ).scalar_one()
    assert case.status == RecoveryCaseStatus.WAITING_FOR_OUTCOME.value
    assert webhook_db_session.execute(
        select(func.count()).select_from(RecoveryOutcome).where(RecoveryOutcome.case_id == case_id)
    ).scalar_one() == 0
    event = webhook_db_session.execute(
        select(WebhookEvent).where(WebhookEvent.provider_event_id == event_id)
    ).scalar_one_or_none()
    assert event is None or event.processing_status != WebhookProcessingStatus.PROCESSED.value


def test_subscription_charged_uses_envelope_timestamp_not_entity_created_at(
    webhook_client,
    webhook_session_factory,
    webhook_db_session,
) -> None:
    sub_id = "sub_ts_charged"
    cycle_start, cycle_end = 1_700_060_000, 1_700_068_000
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
        created_at=1_700_060_010,
    )
    raw_pending, _, _, pending_headers = signed_request(
        build_webhook_payload(
            "subscription.pending",
            subscription=pending,
            created_at=1_700_060_010,
        ),
        event_id="evt_sub_ts_pending",
    )
    post_webhook(webhook_client, raw_pending, pending_headers)

    envelope_ts = 1_700_070_000
    charged = subscription_entity(
        subscription_id=sub_id,
        status="active",
        current_start=cycle_start,
        current_end=cycle_end,
        created_at=1_700_060_010,
    )
    charge_payment = payment_entity(
        payment_id="pay_sub_ts_charged",
        amount=99900,
        status="captured",
    )
    raw_charged, _, _, charged_headers = signed_request(
        build_webhook_payload(
            "subscription.charged",
            subscription=charged,
            payment=charge_payment,
            created_at=envelope_ts,
        ),
        event_id="evt_sub_ts_charged",
    )
    post_webhook(webhook_client, raw_charged, charged_headers)

    webhook_db_session.expire_all()
    key = subscription_pending_source_event_key(sub_id, f"{cycle_start}:{cycle_end}")
    case = webhook_db_session.execute(
        select(RecoveryCase).where(RecoveryCase.source_event_key == key)
    ).scalar_one()
    outcome = webhook_db_session.execute(
        select(RecoveryOutcome).where(RecoveryOutcome.case_id == case.id)
    ).scalar_one()
    expected = datetime.fromtimestamp(envelope_ts, tz=timezone.utc)
    assert outcome.recovered_at.replace(microsecond=0) == expected.replace(microsecond=0)


def test_payment_link_paid_uses_envelope_timestamp(
    webhook_client,
    webhook_session_factory,
    webhook_db_session,
) -> None:
    setup = webhook_session_factory()
    reference = "rq_ts_plink"
    try:
        customer = create_customer(setup, organization_id=DEMO_ORGANIZATION_ID)
        case = create_case(
            setup,
            organization_id=DEMO_ORGANIZATION_ID,
            customer_id=customer.id,
            status=RecoveryCaseStatus.WAITING_FOR_OUTCOME,
        )
        setup.add(
            RecoveryAction(
                organization_id=DEMO_ORGANIZATION_ID,
                case_id=case.id,
                action_type=RecoveryActionType.CREATE_PAYMENT_LINK.value,
                status=RecoveryActionStatus.EXECUTING.value,
                attempt_number=1,
                requires_approval=False,
                idempotency_key=f"plink-ts:{case.id}:1",
                provider_reference=reference,
            )
        )
        setup.commit()
        case_id = case.id
        amount = case.amount_at_risk_minor
    finally:
        setup.close()

    envelope_ts = 1_700_080_000
    link = payment_link_entity(
        reference_id=reference,
        amount=amount,
        created_at=1_700_060_000,
    )
    payment = payment_entity(
        payment_id="pay_ts_plink",
        amount=amount,
        status="captured",
        created_at=1_700_060_000,
    )
    payload = build_webhook_payload(
        "payment_link.paid",
        payment=payment,
        payment_link=link,
        created_at=envelope_ts,
    )
    raw_body, _, _, headers = signed_request(payload, event_id="evt_plink_ts")
    post_webhook(webhook_client, raw_body, headers)

    outcome = webhook_db_session.execute(
        select(RecoveryOutcome).where(RecoveryOutcome.case_id == case_id)
    ).scalar_one()
    expected = datetime.fromtimestamp(envelope_ts, tz=timezone.utc)
    assert outcome.recovered_at.replace(microsecond=0) == expected.replace(microsecond=0)


def test_payment_failed_uses_envelope_timestamp_for_opened_at(
    webhook_client,
    webhook_db_session,
) -> None:
    payment_id = "pay_ts_failed"
    envelope_ts = 1_700_090_000
    payment = payment_entity(payment_id=payment_id, created_at=1_700_060_000)
    payload = build_webhook_payload(
        "payment.failed",
        payment=payment,
        created_at=envelope_ts,
    )
    raw_body, _, _, headers = signed_request(payload, event_id="evt_pay_ts_failed")
    post_webhook(webhook_client, raw_body, headers)

    case = webhook_db_session.execute(
        select(RecoveryCase).where(
            RecoveryCase.source_event_key == f"razorpay:payment_failed:{payment_id}"
        )
    ).scalar_one()
    expected = datetime.fromtimestamp(envelope_ts, tz=timezone.utc)
    assert case.opened_at.replace(microsecond=0) == expected.replace(microsecond=0)
