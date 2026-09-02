"""Razorpay payment read adapter (Prompt 15)."""

from __future__ import annotations

from app.integrations.razorpay.client import RazorpayClient
from app.integrations.razorpay.errors import RazorpayValidationError
from app.integrations.razorpay.schemas import RazorpayPaymentRead


def fetch_payment(client: RazorpayClient, payment_id: str) -> RazorpayPaymentRead:
    """Fetch payment evidence from Razorpay without mutating local state."""
    payload = client.get_json(client.get_payment_path(payment_id))
    try:
        return RazorpayPaymentRead.from_provider_json(payload)
    except ValueError as exc:
        raise RazorpayValidationError("Razorpay payment payload failed validation.") from exc
