"""Recovery downtime context integration tests (Prompt 15)."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.domain.enums import RecoveryActionType
from app.recovery.context import resolve_downtime_context
from app.recovery.service import RecoveryAnalysisService
from tests.integrations.razorpay.razorpay_client_helpers import (
    downtime_collection,
    downtime_item,
    make_mock_client,
)

FAILURE_AT = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)


def test_active_downtime_lookup_normalizes_to_rail_downtime(db_session, analyzable_case) -> None:
    case = analyzable_case
    txn = case.transaction
    assert txn is not None
    txn.payment_method = "upi"
    txn.last_provider_event_at = FAILURE_AT
    db_session.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/payments/downtimes":
            return httpx.Response(
                200,
                json=downtime_collection(
                    downtime_item(
                        id="down_active",
                        method="upi",
                        status="started",
                        begin=int(FAILURE_AT.timestamp()) - 3600,
                        end=int(FAILURE_AT.timestamp()) + 3600,
                    )
                ),
            )
        return httpx.Response(404)

    client = make_mock_client(handler)
    try:
        service = RecoveryAnalysisService(db_session, razorpay_client=client)
        result = service.compute_analysis(case=case)
    finally:
        client.close()

    assert result.ranked_candidates
    action_types = {candidate.action_type for candidate in result.ranked_candidates}
    assert RecoveryActionType.RETRY_SAME_METHOD not in action_types


def test_provider_timeout_still_completes_analysis_with_unknown_downtime(
    db_session,
    analyzable_case,
) -> None:
    case = analyzable_case
    txn = case.transaction
    assert txn is not None
    txn.payment_method = "upi"
    txn.last_provider_event_at = FAILURE_AT
    db_session.commit()

    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout")

    client = make_mock_client(handler)
    try:
        downtime = resolve_downtime_context(client, txn, lookup_configured=True)
        assert downtime.lookup_status == "UNKNOWN"
        service = RecoveryAnalysisService(db_session, razorpay_client=client)
        result = service.compute_analysis(case=case)
    finally:
        client.close()

    assert result.ranked_candidates


def test_unconfigured_lookup_is_unknown_not_no_downtime(db_session, analyzable_case) -> None:
    txn = analyzable_case.transaction
    assert txn is not None
    downtime = resolve_downtime_context(None, txn, lookup_configured=False)
    assert downtime.lookup_status == "UNKNOWN"
    assert downtime.severity == "unknown"

    service = RecoveryAnalysisService(db_session)
    result = service.compute_analysis(case=analyzable_case)
    assert result.ranked_candidates
