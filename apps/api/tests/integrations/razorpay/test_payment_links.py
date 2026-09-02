"""Razorpay Payment Link adapter tests (Prompt 16)."""

from __future__ import annotations

import httpx
import pytest

from app.integrations.razorpay.errors import (
    PaymentLinkSideEffectUnknownError,
    RazorpayAuthenticationError,
    RazorpayRateLimitError,
    RazorpayTimeoutUnknownResult,
    RazorpayTransientError,
    RazorpayValidationError,
)
from app.integrations.razorpay.payment_links import (
    build_payment_link_request_body,
    create_payment_link,
    fetch_payment_links_by_reference,
)
from tests.integrations.razorpay.razorpay_client_helpers import make_mock_client


def test_build_payment_link_request_body_server_authoritative() -> None:
    body = build_payment_link_request_body(
        amount_minor=499900,
        currency="inr",
        reference_id="rl_abc123",
        case_id=__import__("uuid").uuid4(),
        customer_name="Demo",
    )
    assert body["amount"] == 499900
    assert body["currency"] == "INR"
    assert body["accept_partial"] is False
    assert body["reference_id"] == "rl_abc123"
    assert body["notify"] == {"sms": False, "email": False}
    assert body["reminder_enable"] is False


def test_create_payment_link_success() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["auth"] = request.headers.get("Authorization")
        captured["body"] = __import__("json").loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "plink_ok",
                "reference_id": "rl_testref",
                "amount": 10000,
                "currency": "INR",
                "status": "created",
                "short_url": "https://rzp.io/i/abc",
                "accept_partial": False,
            },
        )

    client = make_mock_client(handler)
    try:
        result = create_payment_link(
            client,
            amount_minor=10000,
            currency="INR",
            reference_id="rl_testref",
            case_id=__import__("uuid").uuid4(),
        )
    finally:
        client.close()
    assert captured["path"] == "/v1/payment_links"
    assert captured["auth"] is not None
    assert result.id == "plink_ok"
    assert result.reference_id == "rl_testref"
    assert result.short_url == "https://rzp.io/i/abc"


def test_create_payment_link_reference_mismatch() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "plink_ok",
                "reference_id": "other_ref",
                "amount": 10000,
                "currency": "INR",
                "status": "created",
            },
        )

    client = make_mock_client(handler)
    with pytest.raises(PaymentLinkSideEffectUnknownError):
        try:
            create_payment_link(
                client,
                amount_minor=10000,
                currency="INR",
                reference_id="rl_expected",
                case_id=__import__("uuid").uuid4(),
            )
        finally:
            client.close()


def test_create_payment_link_malformed_2xx() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"reference_id": "rl_x", "amount": 1})

    client = make_mock_client(handler)
    with pytest.raises(PaymentLinkSideEffectUnknownError):
        try:
            create_payment_link(
                client,
                amount_minor=1,
                currency="INR",
                reference_id="rl_x",
                case_id=__import__("uuid").uuid4(),
            )
        finally:
            client.close()


@pytest.mark.parametrize(
    ("status_code", "exception"),
    [
        (400, RazorpayValidationError),
        (401, RazorpayAuthenticationError),
        (429, RazorpayRateLimitError),
        (500, RazorpayTransientError),
        (503, RazorpayTransientError),
    ],
)
def test_create_payment_link_error_mapping(status_code: int, exception: type[Exception]) -> None:
    attempts = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(status_code, json={"error": "fail"})

    client = make_mock_client(handler)
    with pytest.raises(exception):
        try:
            create_payment_link(
                client,
                amount_minor=10000,
                currency="INR",
                reference_id="rl_err",
                case_id=__import__("uuid").uuid4(),
            )
        finally:
            client.close()
    assert attempts["count"] == 1


def test_create_payment_link_timeout_no_retry() -> None:
    attempts = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        raise httpx.ReadTimeout("timeout")

    client = make_mock_client(handler)
    with pytest.raises(RazorpayTimeoutUnknownResult):
        try:
            create_payment_link(
                client,
                amount_minor=10000,
                currency="INR",
                reference_id="rl_timeout",
                case_id=__import__("uuid").uuid4(),
            )
        finally:
            client.close()
    assert attempts["count"] == 1


def test_create_payment_link_transport_error_no_retry() -> None:
    attempts = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        raise httpx.ConnectError("connection reset")

    client = make_mock_client(handler)
    with pytest.raises(RazorpayTransientError):
        try:
            create_payment_link(
                client,
                amount_minor=10000,
                currency="INR",
                reference_id="rl_transport",
                case_id=__import__("uuid").uuid4(),
            )
        finally:
            client.close()
    assert attempts["count"] == 1


def test_fetch_payment_links_by_reference_single_match() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method.upper() == "GET"
        assert "reference_id=rl_match" in str(request.url)
        return httpx.Response(
            200,
            json={
                "entity": "collection",
                "count": 1,
                "items": [
                    {
                        "id": "plink_lookup",
                        "reference_id": "rl_match",
                        "amount": 10000,
                        "currency": "INR",
                        "status": "created",
                        "accept_partial": False,
                    }
                ],
            },
        )

    client = make_mock_client(handler)
    try:
        outcome = fetch_payment_links_by_reference(
            client,
            reference_id="rl_match",
            amount_minor=10000,
            currency="INR",
        )
    finally:
        client.close()
    assert outcome.status == "matched"
    assert outcome.link is not None
    assert outcome.link.id == "plink_lookup"


def test_fetch_payment_links_by_reference_empty() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"entity": "collection", "count": 0, "items": []})

    client = make_mock_client(handler)
    try:
        outcome = fetch_payment_links_by_reference(
            client,
            reference_id="rl_missing",
            amount_minor=10000,
            currency="INR",
        )
    finally:
        client.close()
    assert outcome.status == "not_found"


def test_fetch_payment_links_by_reference_multiple_matches() -> None:
    item = {
        "id": "plink_a",
        "reference_id": "rl_dup",
        "amount": 10000,
        "currency": "INR",
        "status": "created",
        "accept_partial": False,
    }

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"entity": "collection", "count": 2, "items": [item, item]},
        )

    client = make_mock_client(handler)
    try:
        outcome = fetch_payment_links_by_reference(
            client,
            reference_id="rl_dup",
            amount_minor=10000,
            currency="INR",
        )
    finally:
        client.close()
    assert outcome.status == "ambiguous"


def test_fetch_payment_links_by_reference_malformed_get() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": "bad"})

    client = make_mock_client(handler)
    with pytest.raises(RazorpayValidationError):
        try:
            fetch_payment_links_by_reference(
                client,
                reference_id="rl_bad",
                amount_minor=10000,
                currency="INR",
            )
        finally:
            client.close()


def test_fetch_payment_links_by_reference_get_timeout() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout")

    client = make_mock_client(handler)
    with pytest.raises(RazorpayTimeoutUnknownResult):
        try:
            fetch_payment_links_by_reference(
                client,
                reference_id="rl_timeout",
                amount_minor=10000,
                currency="INR",
            )
        finally:
            client.close()
