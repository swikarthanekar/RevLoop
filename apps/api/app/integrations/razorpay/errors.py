"""Typed Razorpay webhook integration errors."""

from __future__ import annotations


class RazorpayWebhookError(Exception):
    """Base error for Razorpay webhook ingestion."""


class MissingWebhookSignatureError(RazorpayWebhookError):
    """Raised when X-Razorpay-Signature header is absent."""


class InvalidWebhookSignatureError(RazorpayWebhookError):
    """Raised when HMAC signature verification fails."""


class MissingWebhookEventIdError(RazorpayWebhookError):
    """Raised when x-razorpay-event-id header is absent."""


class MalformedWebhookPayloadError(RazorpayWebhookError):
    """Raised when verified payload cannot be parsed or is structurally invalid."""


class WebhookConfigurationError(RazorpayWebhookError):
    """Raised when webhook tenant/configuration is missing."""


class WebhookCorrelationError(RazorpayWebhookError):
    """Raised when provider entity cannot be correlated safely."""


class WebhookProcessingError(RazorpayWebhookError):
    """Raised when webhook processing cannot complete safely (retriable)."""
