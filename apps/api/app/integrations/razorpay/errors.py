"""Typed Razorpay integration errors."""

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


class RazorpayApiError(Exception):
    """Base error for Razorpay HTTP API reads."""


class RazorpayConfigurationError(RazorpayApiError):
    """Raised when Razorpay API credentials are missing or blank."""


class RazorpayAuthenticationError(RazorpayApiError):
    """Raised when Razorpay rejects API credentials."""


class RazorpayValidationError(RazorpayApiError):
    """Raised when Razorpay rejects the request or response fails validation."""


class RazorpayRateLimitError(RazorpayApiError):
    """Raised when Razorpay rate-limits the request."""


class RazorpayTransientError(RazorpayApiError):
    """Raised when Razorpay returns a retryable server-side failure."""


class RazorpayTimeoutUnknownResult(RazorpayApiError):
    """Raised when a read times out after bounded retries."""


class RazorpayNotFoundError(RazorpayApiError):
    """Raised when the requested Razorpay resource does not exist."""
