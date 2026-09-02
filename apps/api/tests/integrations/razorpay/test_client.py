"""Razorpay HTTP client tests (Prompt 15)."""

from __future__ import annotations

import httpx
import pytest

from app.integrations.razorpay.client import (
    BACKOFF_BASE_SECONDS,
    BACKOFF_MAX_SECONDS,
    MAX_READ_ATTEMPTS,
    retry_backoff_seconds,
    validate_api_credentials,
)
from app.integrations.razorpay.errors import (
    RazorpayAuthenticationError,
    RazorpayConfigurationError,
    RazorpayNotFoundError,
    RazorpayRateLimitError,
    RazorpayTimeoutUnknownResult,
    RazorpayTransientError,
    RazorpayValidationError,
)
from tests.integrations.razorpay.razorpay_client_helpers import make_mock_client


def _record_sleeps() -> tuple[list[float], object]:
    recorded: list[float] = []

    def recorder(delay_seconds: float) -> None:
        recorded.append(delay_seconds)

    return recorded, recorder


def test_retry_backoff_seconds_exponential_and_capped() -> None:
    assert retry_backoff_seconds(1) == BACKOFF_BASE_SECONDS
    assert retry_backoff_seconds(2) == BACKOFF_BASE_SECONDS * 2
    assert retry_backoff_seconds(3) == BACKOFF_MAX_SECONDS
    assert retry_backoff_seconds(10) == BACKOFF_MAX_SECONDS


def test_timeout_then_success_records_single_backoff() -> None:
    attempts = {"count": 0}
    recorded, recorder = _record_sleeps()

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise httpx.ReadTimeout("timeout")
        return httpx.Response(200, json={"id": "pay_ok"})

    client = make_mock_client(handler, retry_sleep=recorder)
    try:
        payload = client.get_json("/v1/payments/pay_timeout_ok")
    finally:
        client.close()
    assert payload == {"id": "pay_ok"}
    assert attempts["count"] == 2
    assert recorded == [BACKOFF_BASE_SECONDS]


def test_two_503_then_success_records_exponential_backoff() -> None:
    attempts = {"count": 0}
    recorded, recorder = _record_sleeps()

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] <= 2:
            return httpx.Response(503, json={"error": "down"})
        return httpx.Response(200, json={"id": "pay_ok"})

    client = make_mock_client(handler, retry_sleep=recorder)
    try:
        payload = client.get_json("/v1/payments/pay_503_retry")
    finally:
        client.close()
    assert payload == {"id": "pay_ok"}
    assert attempts["count"] == 3
    assert recorded == [BACKOFF_BASE_SECONDS, BACKOFF_BASE_SECONDS * 2]


def test_exhausted_503_retries_records_two_backoffs() -> None:
    attempts = {"count": 0}
    recorded, recorder = _record_sleeps()

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(503, json={"error": "down"})

    client = make_mock_client(handler, retry_sleep=recorder)
    with pytest.raises(RazorpayTransientError):
        try:
            client.get_json("/v1/payments/pay_503_exhausted")
        finally:
            client.close()
    assert attempts["count"] == MAX_READ_ATTEMPTS
    assert recorded == [BACKOFF_BASE_SECONDS, BACKOFF_BASE_SECONDS * 2]


def test_exhausted_timeout_records_two_backoffs() -> None:
    attempts = {"count": 0}
    recorded, recorder = _record_sleeps()

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        raise httpx.ReadTimeout("timeout")

    client = make_mock_client(handler, retry_sleep=recorder)
    with pytest.raises(RazorpayTimeoutUnknownResult):
        try:
            client.get_json("/v1/payments/pay_timeout_exhausted")
        finally:
            client.close()
    assert attempts["count"] == MAX_READ_ATTEMPTS
    assert recorded == [BACKOFF_BASE_SECONDS, BACKOFF_BASE_SECONDS * 2]


def test_401_does_not_sleep_or_retry() -> None:
    attempts = {"count": 0}
    recorded, recorder = _record_sleeps()

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(401, json={"error": "auth"})

    client = make_mock_client(handler, retry_sleep=recorder)
    with pytest.raises(RazorpayAuthenticationError):
        try:
            client.get_json("/v1/payments/pay_401")
        finally:
            client.close()
    assert attempts["count"] == 1
    assert recorded == []


def test_429_does_not_sleep_or_retry() -> None:
    attempts = {"count": 0}
    recorded, recorder = _record_sleeps()

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(429, json={"error": "rate"})

    client = make_mock_client(handler, retry_sleep=recorder)
    with pytest.raises(RazorpayRateLimitError):
        try:
            client.get_json("/v1/payments/pay_429")
        finally:
            client.close()
    assert attempts["count"] == 1
    assert recorded == []


def test_malformed_200_does_not_sleep_or_retry() -> None:
    attempts = {"count": 0}
    recorded, recorder = _record_sleeps()

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(
            200,
            content=b"not-json",
            headers={"Content-Type": "application/json"},
        )

    client = make_mock_client(handler, retry_sleep=recorder)
    with pytest.raises(RazorpayValidationError):
        try:
            client.get_json("/v1/payments/pay_bad_json")
        finally:
            client.close()
    assert attempts["count"] == 1
    assert recorded == []


def test_validate_api_credentials_rejects_blank() -> None:
    with pytest.raises(RazorpayConfigurationError):
        validate_api_credentials(key_id="", key_secret="secret")
    with pytest.raises(RazorpayConfigurationError):
        validate_api_credentials(key_id="key", key_secret="   ")


def test_get_uses_basic_auth_and_trusted_path() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["auth"] = request.headers.get("Authorization", "")
        assert "test_secret_value" not in str(request.url)
        return httpx.Response(200, json={"ok": True})

    client = make_mock_client(handler)
    try:
        payload = client.get_json("/v1/payments/pay_123")
    finally:
        client.close()
    assert payload == {"ok": True}
    assert seen["path"] == "/v1/payments/pay_123"
    assert seen["auth"].startswith("Basic ")


def test_explicit_timeout_configuration() -> None:
    client = make_mock_client(lambda _request: httpx.Response(200, json={}))
    try:
        timeout = client._client.timeout
        assert timeout.connect == 3.0
        assert timeout.read == 8.0
    finally:
        client.close()


def test_validation_error_on_400() -> None:
    client = make_mock_client(lambda _request: httpx.Response(400, json={"error": "bad"}))
    with pytest.raises(RazorpayValidationError):
        try:
            client.get_json("/v1/payments/pay_400")
        finally:
            client.close()


def test_not_found_on_404() -> None:
    client = make_mock_client(lambda _request: httpx.Response(404, json={"error": "missing"}))
    with pytest.raises(RazorpayNotFoundError):
        try:
            client.get_json("/v1/payments/pay_404")
        finally:
            client.close()


def test_5xx_retries_are_bounded() -> None:
    attempts = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(503, json={"error": "down"})

    client = make_mock_client(handler)
    with pytest.raises(RazorpayTransientError):
        try:
            client.get_json("/v1/payments/pay_503")
        finally:
            client.close()
    assert attempts["count"] == MAX_READ_ATTEMPTS


def test_timeout_retries_are_bounded() -> None:
    attempts = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        raise httpx.ReadTimeout("timeout")

    client = make_mock_client(handler)
    with pytest.raises(RazorpayTimeoutUnknownResult):
        try:
            client.get_json("/v1/payments/pay_timeout")
        finally:
            client.close()
    assert attempts["count"] == MAX_READ_ATTEMPTS


def test_successful_retry_after_transient_5xx() -> None:
    attempts = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(502, json={"error": "bad gateway"})
        return httpx.Response(200, json={"id": "pay_ok"})

    client = make_mock_client(handler)
    try:
        payload = client.get_json("/v1/payments/pay_retry_ok")
    finally:
        client.close()
    assert payload["id"] == "pay_ok"
    assert attempts["count"] == 2


def test_empty_provider_id_rejected() -> None:
    client = make_mock_client(lambda _request: httpx.Response(200, json={}))
    with pytest.raises(RazorpayValidationError):
        try:
            client.get_json(client.get_payment_path("   "))
        finally:
            client.close()


def test_provider_id_with_slash_rejected() -> None:
    client = make_mock_client(lambda _request: httpx.Response(200, json={}))
    with pytest.raises(RazorpayValidationError):
        try:
            client.get_json(client.get_payment_path("pay/evil"))
        finally:
            client.close()


def test_provider_id_path_traversal_rejected() -> None:
    client = make_mock_client(lambda _request: httpx.Response(200, json={}))
    with pytest.raises(RazorpayValidationError):
        try:
            client.get_json(client.get_payment_path("../secrets"))
        finally:
            client.close()
