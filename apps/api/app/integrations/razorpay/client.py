"""Razorpay HTTP client for read-only API integration (Prompt 15)."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import Settings
from app.integrations.razorpay.errors import (
    RazorpayAuthenticationError,
    RazorpayConfigurationError,
    RazorpayNotFoundError,
    RazorpayRateLimitError,
    RazorpayTimeoutUnknownResult,
    RazorpayTransientError,
    RazorpayValidationError,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.razorpay.com"
CONNECT_TIMEOUT_SECONDS = 3.0
READ_TIMEOUT_SECONDS = 8.0
MAX_READ_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 0.25
BACKOFF_MAX_SECONDS = 1.0


def retry_backoff_seconds(retry_number: int) -> float:
    """Return bounded exponential delay before the given retry (1-based)."""
    if retry_number < 1:
        raise ValueError("retry_number must be >= 1")
    delay = BACKOFF_BASE_SECONDS * (2 ** (retry_number - 1))
    return min(delay, BACKOFF_MAX_SECONDS)


def _default_retry_sleep(delay_seconds: float) -> None:
    time.sleep(delay_seconds)


def validate_api_credentials(*, key_id: str | None, key_secret: str | None) -> tuple[str, str]:
    if not key_id or not key_id.strip():
        raise RazorpayConfigurationError("Razorpay key ID is not configured.")
    if not key_secret or not key_secret.strip():
        raise RazorpayConfigurationError("Razorpay key secret is not configured.")
    return key_id.strip(), key_secret.strip()


def _encode_provider_id(provider_id: str) -> str:
    if not provider_id or not provider_id.strip():
        raise RazorpayValidationError("Provider resource ID is required.")
    cleaned = provider_id.strip()
    if "/" in cleaned or cleaned in {".", ".."} or ".." in cleaned:
        raise RazorpayValidationError("Provider resource ID is invalid.")
    return quote(cleaned, safe="")


class RazorpayClient:
    """Thin read-only Razorpay HTTP adapter."""

    def __init__(
        self,
        *,
        key_id: str,
        key_secret: str,
        base_url: str = DEFAULT_BASE_URL,
        transport: httpx.BaseTransport | None = None,
        client: httpx.Client | None = None,
        owns_client: bool = False,
        retry_sleep: Callable[[float], None] | None = None,
    ) -> None:
        self._owns_client = owns_client
        self._retry_sleep = retry_sleep or _default_retry_sleep
        timeout = httpx.Timeout(
            connect=CONNECT_TIMEOUT_SECONDS,
            read=READ_TIMEOUT_SECONDS,
            write=READ_TIMEOUT_SECONDS,
            pool=CONNECT_TIMEOUT_SECONDS,
        )
        if client is not None:
            self._client = client
        else:
            self._client = httpx.Client(
                base_url=base_url.rstrip("/"),
                auth=(key_id, key_secret),
                timeout=timeout,
                transport=transport,
            )
            self._owns_client = True

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
        retry_sleep: Callable[[float], None] | None = None,
    ) -> RazorpayClient:
        key_id, key_secret = validate_api_credentials(
            key_id=settings.razorpay_key_id.get_secret_value(),
            key_secret=settings.razorpay_key_secret.get_secret_value(),
        )
        return cls(
            key_id=key_id,
            key_secret=key_secret,
            transport=transport,
            retry_sleep=retry_sleep,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> RazorpayClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def get_json(self, path: str) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, MAX_READ_ATTEMPTS + 1):
            try:
                response = self._client.get(path)
            except httpx.TimeoutException as exc:
                last_error = RazorpayTimeoutUnknownResult("Razorpay read timed out.")
                if attempt < MAX_READ_ATTEMPTS:
                    self._retry_sleep(retry_backoff_seconds(attempt))
                    continue
                raise last_error from exc
            except httpx.TransportError as exc:
                last_error = RazorpayTransientError("Razorpay transport failure.")
                if attempt < MAX_READ_ATTEMPTS:
                    self._retry_sleep(retry_backoff_seconds(attempt))
                    continue
                raise last_error from exc

            if response.status_code in {401, 403}:
                raise RazorpayAuthenticationError("Razorpay authentication failed.")
            if response.status_code == 400:
                raise RazorpayValidationError("Razorpay rejected the request.")
            if response.status_code == 404:
                raise RazorpayNotFoundError("Razorpay resource not found.")
            if response.status_code == 429:
                raise RazorpayRateLimitError("Razorpay rate limit exceeded.")
            if response.status_code >= 500:
                last_error = RazorpayTransientError("Razorpay server error.")
                if attempt < MAX_READ_ATTEMPTS:
                    logger.warning(
                        "Razorpay GET retry after status %s (attempt %s)",
                        response.status_code,
                        attempt,
                    )
                    self._retry_sleep(retry_backoff_seconds(attempt))
                    continue
                raise last_error

            if response.status_code >= 400:
                raise RazorpayValidationError(
                    f"Razorpay request failed with status {response.status_code}."
                )

            try:
                payload = response.json()
            except json.JSONDecodeError as exc:
                raise RazorpayValidationError("Razorpay response is not valid JSON.") from exc
            if not isinstance(payload, dict):
                raise RazorpayValidationError("Razorpay response must be a JSON object.")
            return payload

        assert last_error is not None
        raise last_error

    def post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        """Single-attempt POST for mutating Razorpay operations (no automatic retry)."""
        try:
            response = self._client.post(path, json=body)
        except httpx.TimeoutException as exc:
            raise RazorpayTimeoutUnknownResult("Razorpay write timed out.") from exc
        except httpx.TransportError as exc:
            raise RazorpayTransientError("Razorpay transport failure.") from exc

        if response.status_code in {401, 403}:
            raise RazorpayAuthenticationError("Razorpay authentication failed.")
        if response.status_code == 400:
            raise RazorpayValidationError("Razorpay rejected the request.")
        if response.status_code == 404:
            raise RazorpayNotFoundError("Razorpay resource not found.")
        if response.status_code == 429:
            raise RazorpayRateLimitError("Razorpay rate limit exceeded.")
        if response.status_code >= 500:
            raise RazorpayTransientError("Razorpay server error.")

        if response.status_code >= 400:
            raise RazorpayValidationError(
                f"Razorpay request failed with status {response.status_code}."
            )

        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise RazorpayValidationError("Razorpay response is not valid JSON.") from exc
        if not isinstance(payload, dict):
            raise RazorpayValidationError("Razorpay response must be a JSON object.")
        return payload

    def get_payment_path(self, payment_id: str) -> str:
        return f"/v1/payments/{_encode_provider_id(payment_id)}"

    def get_downtimes_path(self) -> str:
        return "/v1/payments/downtimes"

    def get_downtime_path(self, downtime_id: str) -> str:
        return f"/v1/payments/downtimes/{_encode_provider_id(downtime_id)}"

    def get_payment_links_path(self) -> str:
        return "/v1/payment_links"

    def get_payment_links_by_reference_path(self, reference_id: str) -> str:
        encoded = quote(reference_id.strip(), safe="")
        return f"/v1/payment_links/?reference_id={encoded}"
