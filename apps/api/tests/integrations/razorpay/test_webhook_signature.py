"""Razorpay webhook signature verification tests."""

from __future__ import annotations

import json
import uuid

from sqlalchemy import func, select

from app.models.recovery_case import RecoveryCase
from app.models.transaction import Transaction
from app.models.webhook_event import WebhookEvent
from tests.integrations.razorpay.conftest import post_webhook
from tests.integrations.razorpay.helpers import (
    WEBHOOK_SECRET,
    build_webhook_payload,
    encode_payload,
    payment_entity,
    sign_raw_body,
    signed_request,
)


def _count_webhook_events(session) -> int:
    return session.execute(select(func.count()).select_from(WebhookEvent)).scalar_one()


def _count_transactions(session) -> int:
    return session.execute(select(func.count()).select_from(Transaction)).scalar_one()


def _count_recovery_cases(session) -> int:
    return session.execute(select(func.count()).select_from(RecoveryCase)).scalar_one()


def test_valid_signature_accepted(webhook_client, webhook_db_session) -> None:
    payment = payment_entity(payment_id="pay_sig_ok_001")
    payload = build_webhook_payload("payment.failed", payment=payment)
    raw_body, _, _, headers = signed_request(payload, event_id="evt_sig_ok_001")
    response = post_webhook(webhook_client, raw_body, headers)
    assert response.status_code == 204
    assert _count_webhook_events(webhook_db_session) >= 1


def test_invalid_signature_rejected(webhook_client, webhook_db_session) -> None:
    payment = payment_entity(payment_id="pay_sig_bad_001")
    payload = build_webhook_payload("payment.failed", payment=payment)
    raw_body, _, _, headers = signed_request(payload, event_id="evt_sig_bad_001")
    headers["X-Razorpay-Signature"] = "deadbeef" * 8
    before = _count_webhook_events(webhook_db_session)
    txn_before = _count_transactions(webhook_db_session)
    response = post_webhook(webhook_client, raw_body, headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_WEBHOOK_SIGNATURE"
    assert _count_webhook_events(webhook_db_session) == before
    assert _count_transactions(webhook_db_session) == txn_before


def test_missing_signature_rejected(webhook_client, webhook_db_session) -> None:
    payment = payment_entity(payment_id="pay_sig_missing_001")
    payload = build_webhook_payload("payment.failed", payment=payment)
    raw_body = encode_payload(payload)
    headers = {"x-razorpay-event-id": "evt_sig_missing_001", "Content-Type": "application/json"}
    before = webhook_db_session.execute(select(func.count()).select_from(WebhookEvent)).scalar_one()
    response = post_webhook(webhook_client, raw_body, headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "MISSING_WEBHOOK_SIGNATURE"
    after = webhook_db_session.execute(select(func.count()).select_from(WebhookEvent)).scalar_one()
    assert after == before


def test_body_modified_after_signature_rejected(webhook_client) -> None:
    payment = payment_entity(payment_id="pay_sig_tamper_001", amount=100)
    payload = build_webhook_payload("payment.failed", payment=payment)
    raw_body, _, _, headers = signed_request(payload, event_id="evt_sig_tamper_001")
    tampered = json.loads(raw_body.decode())
    tampered["payload"]["payment"]["entity"]["amount"] = 200
    tampered_body = encode_payload(tampered)
    response = post_webhook(webhook_client, tampered_body, headers)
    assert response.status_code == 401


def test_whitespace_changes_signature(webhook_client) -> None:
    payment = payment_entity(payment_id="pay_sig_ws_001")
    payload = build_webhook_payload("payment.failed", payment=payment)
    compact = encode_payload(payload)
    signature = sign_raw_body(compact)
    pretty = json.dumps(payload, indent=2).encode("utf-8")
    headers = {
        "X-Razorpay-Signature": signature,
        "x-razorpay-event-id": "evt_sig_ws_001",
        "Content-Type": "application/json",
    }
    response = post_webhook(webhook_client, pretty, headers)
    assert response.status_code == 401


def test_malformed_json_with_valid_hmac_returns_400(webhook_client, webhook_db_session) -> None:
    raw_body = b"{not-json"
    signature = sign_raw_body(raw_body)
    headers = {
        "X-Razorpay-Signature": signature,
        "x-razorpay-event-id": f"evt_bad_json_{uuid.uuid4().hex[:8]}",
    }
    before = webhook_db_session.execute(select(func.count()).select_from(WebhookEvent)).scalar_one()
    response = post_webhook(webhook_client, raw_body, headers)
    assert response.status_code == 400
    after = webhook_db_session.execute(select(func.count()).select_from(WebhookEvent)).scalar_one()
    assert after == before


def test_invalid_signature_zero_db_writes(webhook_client, webhook_db_session) -> None:
    payment = payment_entity(payment_id="pay_zero_write_001")
    payload = build_webhook_payload("payment.failed", payment=payment)
    raw_body, _, _, headers = signed_request(payload, event_id="evt_zero_write_001")
    headers["X-Razorpay-Signature"] = sign_raw_body(b"tampered", WEBHOOK_SECRET)
    before_cases = _count_recovery_cases(webhook_db_session)
    response = post_webhook(webhook_client, raw_body, headers)
    assert response.status_code == 401
    after_cases = _count_recovery_cases(webhook_db_session)
    assert after_cases == before_cases
