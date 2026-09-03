"""Shared helpers for the Prompt 24 P0 integration suite."""

from __future__ import annotations

import time
from typing import Any

from tests.integrations.razorpay.helpers import payment_entity, signed_request

WEBHOOK_PATH = "/api/v1/webhooks/razorpay"
DASHBOARD_PATH = "/api/v1/dashboard/summary"

#: A sentinel planted in webhook input fields that must never reach the public
#: timeline. Distinctive enough that a substring search cannot match by accident.
SENSITIVE_SENTINEL = "zzsentinel-leak-canary-9f3a"

DEFAULT_AMOUNT_MINOR = 499_900


def recent_epoch(offset_seconds: int = 3600) -> int:
    """A failure timestamp close to now.

    The model consumes `hours_since_failure`, so a fixture dated years in the
    past scores near zero and the engine correctly recommends STOP. A realistic
    recent failure is what exercises the intervention path.
    """
    return int(time.time()) - offset_seconds


def failure_payload(
    *,
    payment_id: str,
    customer_external_id: str,
    amount_minor: int = DEFAULT_AMOUNT_MINOR,
    created_at: int | None = None,
    with_sentinel: bool = False,
) -> dict[str, Any]:
    """A qualifying `payment.failed` envelope correlated to one customer.

    Each test supplies its own customer. Recovery features include the
    customer's recent failure and contact history, so sharing one customer
    across tests would let earlier tests shift later recommendations — the
    engine would legitimately start demanding approval as the history worsens.
    """
    occurred_at = created_at if created_at is not None else recent_epoch()
    payment = payment_entity(payment_id=payment_id, amount=amount_minor)
    payment["created_at"] = occurred_at
    payment["notes"] = {"revloop_customer": customer_external_id}
    if with_sentinel:
        # Sensitive-looking input that the timeline allowlist must drop.
        payment["email"] = f"{SENSITIVE_SENTINEL}@example.com"
        payment["contact"] = "+919000000000"
        payment["error_description"] = f"raw provider prose {SENSITIVE_SENTINEL}"
        payment["notes"] = dict(payment.get("notes") or {})
        payment["notes"]["internal_note"] = SENSITIVE_SENTINEL
    return {
        "event": "payment.failed",
        "created_at": occurred_at,
        "payload": {"payment": {"entity": payment}},
    }


def payment_link_paid_payload(
    *,
    reference_id: str,
    payment_id: str,
    amount_minor: int = DEFAULT_AMOUNT_MINOR,
    currency: str = "INR",
    created_at: int | None = None,
) -> dict[str, Any]:
    """A `payment_link.paid` envelope correlated to a real recovery action."""
    occurred_at = created_at if created_at is not None else recent_epoch(offset_seconds=60)
    payment = payment_entity(payment_id=payment_id, amount=amount_minor)
    payment["status"] = "captured"
    payment["created_at"] = occurred_at
    return {
        "event": "payment_link.paid",
        "created_at": occurred_at,
        "payload": {
            "payment_link": {
                "entity": {
                    "id": f"plink_{reference_id[-12:]}",
                    "entity": "payment_link",
                    "reference_id": reference_id,
                    "amount": amount_minor,
                    "currency": currency,
                    "status": "paid",
                }
            },
            "payment": {"entity": payment},
        },
    }


def post_webhook(client, payload: dict[str, Any], *, event_id: str):
    """Post a signed webhook through the real HTTP boundary."""
    raw_body, _signature, _event_id, headers = signed_request(payload, event_id=event_id)
    return client.post(WEBHOOK_PATH, content=raw_body, headers=headers)


def dashboard_recovered_minor(client, headers: dict[str, str]) -> int:
    response = client.get(DASHBOARD_PATH, headers=headers)
    assert response.status_code == 200, response.text
    return int(response.json()["revenue_recovered_minor"])
