"""Razorpay payment read tests (Prompt 15)."""

from __future__ import annotations

import httpx
import pytest

from app.integrations.razorpay.errors import RazorpayValidationError
from app.integrations.razorpay.payments import fetch_payment
from tests.integrations.razorpay.razorpay_client_helpers import (
    make_mock_client,
    payment_payload,
)


def test_fetch_payment_returns_typed_dto() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/payments/pay_read_001"
        return httpx.Response(200, json=payment_payload(id="pay_read_001", status="captured"))

    client = make_mock_client(handler)
    try:
        payment = fetch_payment(client, "pay_read_001")
    finally:
        client.close()
    assert payment.id == "pay_read_001"
    assert payment.amount == 499900
    assert payment.currency == "INR"
    assert payment.status == "captured"


def test_malformed_payment_2xx_rejected() -> None:
    client = make_mock_client(
        lambda _request: httpx.Response(200, json={"id": "pay_bad", "amount": "not-int"})
    )
    with pytest.raises(RazorpayValidationError):
        try:
            fetch_payment(client, "pay_bad")
        finally:
            client.close()
