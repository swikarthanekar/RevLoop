"""Test helpers for Razorpay webhook tests (independent HMAC construction)."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from typing import Any

WEBHOOK_SECRET = "dev-razorpay-webhook-secret"


def sign_raw_body(raw_body: bytes, secret: str = WEBHOOK_SECRET) -> str:
    """Compute expected signature without calling production verify code."""
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def encode_payload(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def payment_entity(
    *,
    payment_id: str | None = None,
    amount: int = 499900,
    currency: str = "INR",
    status: str = "failed",
    created_at: int = 1_700_000_000,
    customer_external_id: str = "demo-customer-0001",
    method: str = "upi",
) -> dict[str, Any]:
    return {
        "id": payment_id or f"pay_{uuid.uuid4().hex[:14]}",
        "amount": amount,
        "currency": currency,
        "status": status,
        "method": method,
        "created_at": created_at,
        "notes": {"revloop_customer": customer_external_id},
        "error_code": "BAD_REQUEST_ERROR",
        "error_reason": "payment_failed",
    }


def subscription_entity(
    *,
    subscription_id: str | None = None,
    status: str = "pending",
    created_at: int = 1_700_000_000,
    current_start: int = 1_699_000_000,
    current_end: int | None = None,
    customer_external_id: str = "demo-customer-0001",
    notes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    entity: dict[str, Any] = {
        "id": subscription_id or f"sub_{uuid.uuid4().hex[:14]}",
        "status": status,
        "created_at": created_at,
        "current_start": current_start,
        "notes": notes if notes is not None else {"revloop_customer": customer_external_id},
    }
    if current_end is not None:
        entity["current_end"] = current_end
    return entity


def payment_link_entity(
    *,
    link_id: str | None = None,
    reference_id: str | None = None,
    amount: int = 499900,
    currency: str = "INR",
    created_at: int = 1_700_000_000,
) -> dict[str, Any]:
    return {
        "id": link_id or f"plink_{uuid.uuid4().hex[:14]}",
        "amount": amount,
        "currency": currency,
        "status": "paid",
        "reference_id": reference_id,
        "created_at": created_at,
        "notes": {},
    }


def build_webhook_payload(
    event: str,
    *,
    payment: dict[str, Any] | None = None,
    subscription: dict[str, Any] | None = None,
    payment_link: dict[str, Any] | None = None,
    created_at: int | None = 1_700_000_000,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"event": event, "payload": {}}
    if created_at is not None:
        payload["created_at"] = created_at
    if payment is not None:
        payload["payload"]["payment"] = {"entity": payment}
    if subscription is not None:
        payload["payload"]["subscription"] = {"entity": subscription}
    if payment_link is not None:
        payload["payload"]["payment_link"] = {"entity": payment_link}
    return payload


def signed_request(
    payload: dict[str, Any],
    *,
    event_id: str | None = None,
    secret: str = WEBHOOK_SECRET,
) -> tuple[bytes, str, str, dict[str, str]]:
    raw_body = encode_payload(payload)
    signature = sign_raw_body(raw_body, secret)
    provider_event_id = event_id or f"evt_{uuid.uuid4().hex}"
    headers = {
        "X-Razorpay-Signature": signature,
        "x-razorpay-event-id": provider_event_id,
        "Content-Type": "application/json",
    }
    return raw_body, signature, provider_event_id, headers
