"""Razorpay webhook signature verification (Prompt 14)."""

from __future__ import annotations

import hashlib
import hmac

from app.integrations.razorpay.errors import (
    InvalidWebhookSignatureError,
    MissingWebhookSignatureError,
    WebhookConfigurationError,
)


def verify_webhook_signature(
    *,
    raw_body: bytes,
    received_signature: str | None,
    webhook_secret: str,
) -> None:
    """Verify HMAC-SHA256 signature against exact raw request bytes."""
    if not webhook_secret or not webhook_secret.strip():
        raise WebhookConfigurationError("Webhook secret is not configured.")
    if not received_signature:
        raise MissingWebhookSignatureError("Missing X-Razorpay-Signature header.")
    expected = hmac.new(
        webhook_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, received_signature):
        raise InvalidWebhookSignatureError("Invalid Razorpay webhook signature.")
