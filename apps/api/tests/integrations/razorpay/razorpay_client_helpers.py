"""Shared helpers for Razorpay HTTP client tests."""

from __future__ import annotations

from collections.abc import Callable

import httpx

from app.integrations.razorpay.client import RazorpayClient


def make_mock_client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    retry_sleep: Callable[[float], None] | None = None,
) -> RazorpayClient:
    transport = httpx.MockTransport(handler)
    return RazorpayClient(
        key_id="rzp_test_key",
        key_secret="test_secret_value",
        transport=transport,
        retry_sleep=retry_sleep or (lambda _delay: None),
    )


def json_response(status_code: int, payload: object) -> httpx.Response:
    return httpx.Response(status_code, json=payload)


def payment_payload(**overrides: object) -> dict:
    base = {
        "id": "pay_test_001",
        "entity": "payment",
        "amount": 499900,
        "currency": "INR",
        "status": "failed",
        "method": "upi",
        "order_id": "order_test_001",
        "created_at": 1_700_000_000,
        "captured": False,
    }
    base.update(overrides)
    return base


def downtime_collection(*items: dict) -> dict:
    return {
        "payment_downtime": {
            "entity": "collection",
            "count": len(items),
            "items": list(items),
        }
    }


def downtime_item(**overrides: object) -> dict:
    base = {
        "id": "down_test_001",
        "entity": "payment.downtime",
        "method": "upi",
        "status": "started",
        "severity": "high",
        "scheduled": False,
        "begin": 1_699_999_000,
        "end": 1_700_001_000,
        "instrument": {},
    }
    base.update(overrides)
    return base
