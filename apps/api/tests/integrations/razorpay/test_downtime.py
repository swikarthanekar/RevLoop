"""Razorpay downtime read + matching tests (Prompt 15)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest

from app.integrations.razorpay.downtime import (
    build_downtime_context_from_records,
    evaluate_downtime_match,
    fetch_downtime_by_id,
    fetch_downtimes,
)
from app.integrations.razorpay.errors import RazorpayValidationError
from app.integrations.razorpay.schemas import PaymentDowntime
from app.recovery.context import resolve_downtime_context_for_transaction
from app.recovery.schemas import DowntimeContext
from tests.integrations.razorpay.razorpay_client_helpers import (
    downtime_collection,
    downtime_item,
    make_mock_client,
)

FAILURE_AT = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)


def _record(**overrides: object) -> PaymentDowntime:
    base = {
        "begin": int(FAILURE_AT.timestamp()) - 3600,
        "end": int(FAILURE_AT.timestamp()) + 3600,
    }
    base.update(overrides)
    return PaymentDowntime.from_provider_json(downtime_item(**base))


def test_fetch_downtimes_uses_list_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/payments/downtimes"
        return httpx.Response(200, json=downtime_collection())

    client = make_mock_client(handler)
    try:
        records = fetch_downtimes(client)
    finally:
        client.close()
    assert records == []


def test_fetch_downtime_by_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/payments/downtimes/down_one"
        return httpx.Response(200, json=downtime_item(id="down_one"))

    client = make_mock_client(handler)
    try:
        record = fetch_downtime_by_id(client, "down_one")
    finally:
        client.close()
    assert record.id == "down_one"


def test_malformed_downtime_collection_rejected() -> None:
    client = make_mock_client(
        lambda _request: httpx.Response(200, json={"payment_downtime": "not-an-object"})
    )
    with pytest.raises(RazorpayValidationError):
        try:
            fetch_downtimes(client)
        finally:
            client.close()


def test_official_empty_collection_parses_to_empty_list() -> None:
    payload = {
        "payment_downtime": {
            "entity": "collection",
            "count": 0,
            "items": [],
        }
    }

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client = make_mock_client(handler)
    try:
        records = fetch_downtimes(client)
    finally:
        client.close()
    assert records == []

    ctx = build_downtime_context_from_records(
        records,
        payment_method="upi",
        failure_at=FAILURE_AT,
        instrument=None,
    )
    assert ctx.lookup_status == "NO_DOWNTIME"
    assert ctx.rail_degraded is False
    assert ctx.severity == "none"


def test_malformed_official_envelope_cases() -> None:
    cases = [
        {},
        {"payment_downtime": {"entity": "collection", "count": 1, "items": "bad"}},
        {
            "payment_downtime": {
                "entity": "collection",
                "count": 1,
                "items": [{"method": "upi", "status": "started"}],
            }
        },
        {
            "payment_downtime": {
                "entity": "collection",
                "count": 1,
                "items": [
                    {
                        "id": "down_bad_ts",
                        "method": "upi",
                        "status": "started",
                        "begin": "not-a-unix-ts",
                    }
                ],
            }
        },
    ]
    for payload in cases:

        def handler(_request: httpx.Request, body: dict = payload) -> httpx.Response:
            return httpx.Response(200, json=body)

        client = make_mock_client(handler)
        with pytest.raises(RazorpayValidationError):
            try:
                fetch_downtimes(client)
            finally:
                client.close()


def test_status_started_matches() -> None:
    record = _record(method="card", status="started")
    assert (
        evaluate_downtime_match(
            record,
            payment_method="card",
            failure_at=FAILURE_AT,
            instrument=None,
        )
        == "MATCH"
    )


def test_status_updated_is_active() -> None:
    record = _record(
        method="card",
        status="updated",
        begin=int(FAILURE_AT.timestamp()) - 3600,
        end=None,
        instrument={"network": "VISA"},
    )
    ctx = build_downtime_context_from_records(
        [record],
        payment_method="card",
        failure_at=FAILURE_AT,
        instrument={"network": "VISA"},
    )
    assert ctx.lookup_status == "KNOWN"
    assert ctx.rail_degraded is True


def test_status_scheduled_before_begin_is_no_match() -> None:
    future_begin = datetime(2026, 2, 1, tzinfo=timezone.utc)
    record = _record(
        method="upi",
        status="scheduled",
        scheduled=True,
        begin=int(future_begin.timestamp()),
    )
    assert (
        evaluate_downtime_match(
            record,
            payment_method="upi",
            failure_at=FAILURE_AT,
            instrument=None,
        )
        == "NO_MATCH"
    )


def test_unknown_status_with_matching_context_is_uncertain() -> None:
    record = _record(method="upi", status="provider_new_status")
    assert (
        evaluate_downtime_match(
            record,
            payment_method="upi",
            failure_at=FAILURE_AT,
            instrument=None,
        )
        == "UNCERTAIN"
    )
    ctx = build_downtime_context_from_records(
        [record],
        payment_method="upi",
        failure_at=FAILURE_AT,
        instrument=None,
    )
    assert ctx.lookup_status == "UNKNOWN"


def test_unknown_status_method_mismatch_is_no_match_not_global_unknown() -> None:
    record = _record(method="upi", status="provider_new_status")
    ctx = build_downtime_context_from_records(
        [record],
        payment_method="card",
        failure_at=FAILURE_AT,
        instrument=None,
    )
    assert ctx.lookup_status == "NO_DOWNTIME"


def test_matching_method_instrument_active_window() -> None:
    record = _record(method="upi", status="started", instrument={"issuer": "HDFC"})
    assert (
        evaluate_downtime_match(
            record,
            payment_method="upi",
            failure_at=FAILURE_AT,
            instrument={"issuer": "HDFC"},
        )
        == "MATCH"
    )


def test_upi_downtime_does_not_match_card_failure() -> None:
    record = _record(method="upi", status="started")
    assert (
        evaluate_downtime_match(
            record,
            payment_method="card",
            failure_at=FAILURE_AT,
            instrument=None,
        )
        == "NO_MATCH"
    )


def test_issuer_mismatch_not_a_match() -> None:
    record = _record(method="card", status="started", instrument={"issuer": "HDFC"})
    assert (
        evaluate_downtime_match(
            record,
            payment_method="card",
            failure_at=FAILURE_AT,
            instrument={"issuer": "ICICI"},
        )
        == "NO_MATCH"
    )


def test_future_scheduled_downtime_not_active_match() -> None:
    future_begin = datetime(2026, 2, 1, tzinfo=timezone.utc)
    record = _record(
        method="upi",
        status="started",
        scheduled=True,
        begin=int(future_begin.timestamp()),
        end=int(future_begin.timestamp()) + 3600,
    )
    assert (
        evaluate_downtime_match(
            record,
            payment_method="upi",
            failure_at=FAILURE_AT,
            instrument=None,
        )
        == "NO_MATCH"
    )


def test_ended_downtime_not_active_match() -> None:
    record = _record(method="upi", status="resolved")
    assert (
        evaluate_downtime_match(
            record,
            payment_method="upi",
            failure_at=FAILURE_AT,
            instrument=None,
        )
        == "NO_MATCH"
    )


def test_failure_before_begin_not_a_match() -> None:
    begin = datetime(2026, 1, 20, tzinfo=timezone.utc)
    record = _record(
        method="upi",
        status="started",
        begin=int(begin.timestamp()),
        end=int(begin.timestamp()) + 3600,
    )
    assert (
        evaluate_downtime_match(
            record,
            payment_method="upi",
            failure_at=FAILURE_AT,
            instrument=None,
        )
        == "NO_MATCH"
    )


def test_failure_after_end_not_a_match() -> None:
    begin = datetime(2026, 1, 10, tzinfo=timezone.utc)
    end = datetime(2026, 1, 12, tzinfo=timezone.utc)
    record = _record(
        method="upi",
        status="started",
        begin=int(begin.timestamp()),
        end=int(end.timestamp()),
    )
    assert (
        evaluate_downtime_match(
            record,
            payment_method="upi",
            failure_at=FAILURE_AT,
            instrument=None,
        )
        == "NO_MATCH"
    )


def test_unscoped_active_downtime_matches_method_and_time() -> None:
    ctx = build_downtime_context_from_records(
        [_record(method="upi", status="started")],
        payment_method="upi",
        failure_at=FAILURE_AT,
        instrument=None,
    )
    assert ctx.lookup_status == "KNOWN"
    assert ctx.rail_degraded is True


def test_missing_instrument_evidence_is_unknown_not_false_positive() -> None:
    ctx = build_downtime_context_from_records(
        [_record(method="card", status="started", instrument={"issuer": "HDFC"})],
        payment_method="card",
        failure_at=FAILURE_AT,
        instrument=None,
    )
    assert ctx.lookup_status == "UNKNOWN"
    assert ctx.rail_degraded is False


def test_multiple_records_only_relevant_controls_result() -> None:
    ctx = build_downtime_context_from_records(
        [
            _record(id="down_upi", method="upi", status="started"),
            _record(id="down_card", method="card", status="started"),
        ],
        payment_method="upi",
        failure_at=FAILURE_AT,
        instrument=None,
    )
    assert ctx.lookup_status == "KNOWN"
    assert ctx.matched_method == "upi"


def test_empty_successful_collection_is_no_downtime() -> None:
    ctx = build_downtime_context_from_records(
        [],
        payment_method="upi",
        failure_at=FAILURE_AT,
        instrument=None,
    )
    assert ctx == DowntimeContext(
        lookup_status="NO_DOWNTIME",
        rail_degraded=False,
        severity="none",
    )


def test_unknown_vs_no_downtime_side_by_side() -> None:
    empty_ctx = build_downtime_context_from_records(
        [],
        payment_method="upi",
        failure_at=FAILURE_AT,
        instrument=None,
    )
    assert empty_ctx.lookup_status == "NO_DOWNTIME"

    uncertain_ctx = build_downtime_context_from_records(
        [_record(method="card", status="started", instrument={"issuer": "HDFC"})],
        payment_method="card",
        failure_at=FAILURE_AT,
        instrument=None,
    )
    assert uncertain_ctx.lookup_status == "UNKNOWN"

    txn = SimpleNamespace(
        payment_method="upi",
        last_provider_event_at=FAILURE_AT,
        provider_created_at=FAILURE_AT,
        metadata_={},
    )

    def timeout_handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout")

    timeout_client = make_mock_client(timeout_handler)
    try:
        timeout_ctx = resolve_downtime_context_for_transaction(timeout_client, txn)
    finally:
        timeout_client.close()
    assert timeout_ctx.lookup_status == "UNKNOWN"

    error_client = make_mock_client(lambda _request: httpx.Response(503, json={"error": "down"}))
    try:
        error_ctx = resolve_downtime_context_for_transaction(error_client, txn)
    finally:
        error_client.close()
    assert error_ctx.lookup_status == "UNKNOWN"

    malformed_client = make_mock_client(
        lambda _request: httpx.Response(
            200,
            json={"payment_downtime": {"entity": "collection", "count": 0, "items": "bad"}},
        )
    )
    try:
        malformed_ctx = resolve_downtime_context_for_transaction(malformed_client, txn)
    finally:
        malformed_client.close()
    assert malformed_ctx.lookup_status == "UNKNOWN"

    assert empty_ctx.lookup_status != timeout_ctx.lookup_status
