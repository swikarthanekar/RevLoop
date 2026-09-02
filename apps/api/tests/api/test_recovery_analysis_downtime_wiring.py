"""Runtime wiring tests for Razorpay downtime reads on /analyze (Prompt 15 hardening)."""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.auth import AuthContext, get_current_user
from app.core.config import Settings, get_settings
from app.core.deps import get_db
from app.demo.constants import DEMO_AUTH_USER_ANALYST_ID, DEMO_ORGANIZATION_ID
from app.domain.enums import RecoveryActionType, UserRole
from app.main import create_app
from app.models.recovery_recommendation import RecoveryRecommendation
from app.models.transaction import Transaction
from app.recovery import service as recovery_service_module
from app.recovery.schemas import DowntimeContext
from tests.api.conftest import DEMO_AUTH_HEADERS
from tests.demo.conftest import postgres_available
from tests.integrations.razorpay.razorpay_client_helpers import (
    downtime_collection,
    downtime_item,
    make_mock_client,
)

pytestmark = pytest.mark.skipif(
    not postgres_available(),
    reason="PostgreSQL not available (set REVLOOP_TEST_DATABASE_URL)",
)

FAILURE_AT = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)


def _build_client(
    *,
    seeded_database,
    settings: Settings,
    monkeypatch,
) -> TestClient:
    captured: dict[str, DowntimeContext] = {}
    original_resolve = recovery_service_module.resolve_downtime_context

    def spy_resolve(client, transaction, *, lookup_configured: bool) -> DowntimeContext:
        result = original_resolve(
            client,
            transaction,
            lookup_configured=lookup_configured,
        )
        captured["downtime"] = result
        return result

    monkeypatch.setattr(recovery_service_module, "resolve_downtime_context", spy_resolve)

    app = create_app()

    def override_get_db() -> Generator[Session, None, None]:
        session = sessionmaker(bind=seeded_database, autoflush=False, autocommit=False)()
        try:
            yield session
        finally:
            session.close()

    async def override_get_current_user() -> AuthContext:
        return AuthContext(
            user_id=DEMO_AUTH_USER_ANALYST_ID,
            organization_id=DEMO_ORGANIZATION_ID,
            role=UserRole.ANALYST,
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_current_user] = override_get_current_user

    client = TestClient(app, raise_server_exceptions=False)
    client.captured_downtime = captured  # type: ignore[attr-defined]
    return client


def test_analyze_runtime_path_uses_provider_downtime_evidence(
    seeded_database,
    api_demo_settings,
    analyzable_case,
    fresh_db_session,
    monkeypatch,
) -> None:
    txn = fresh_db_session.get(Transaction, analyzable_case.transaction_id)
    assert txn is not None
    txn.payment_method = "upi"
    txn.last_provider_event_at = FAILURE_AT
    fresh_db_session.commit()
    case_id = analyzable_case.id

    configured_settings = api_demo_settings.model_copy(
        update={
            "razorpay_key_id": SecretStr("rzp_test_runtime"),
            "razorpay_key_secret": SecretStr("runtime_secret_value"),
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/payments/downtimes":
            return httpx.Response(
                200,
                json=downtime_collection(
                    downtime_item(
                        id="down_runtime",
                        method="upi",
                        status="started",
                        begin=int(FAILURE_AT.timestamp()) - 3600,
                        end=int(FAILURE_AT.timestamp()) + 3600,
                    )
                ),
            )
        raise AssertionError(f"unexpected provider request: {request.url.path}")

    def mock_create_read_client(_settings: Settings, *, transport=None):
        return make_mock_client(handler)

    monkeypatch.setattr(
        "app.integrations.razorpay.provider.create_razorpay_read_client",
        mock_create_read_client,
    )

    client = _build_client(
        seeded_database=seeded_database,
        settings=configured_settings,
        monkeypatch=monkeypatch,
    )
    response = client.post(
        f"/api/v1/recovery-cases/{case_id}/analyze",
        headers=DEMO_AUTH_HEADERS,
        json={"reason": "MANUAL_ANALYSIS"},
    )
    assert response.status_code == 200
    payload = response.json()
    action_types = {item["action_type"] for item in payload["candidates"]}
    assert RecoveryActionType.RETRY_SAME_METHOD.value not in action_types

    run_id = UUID(payload["analysis_run_id"])
    rows = fresh_db_session.execute(
        select(RecoveryRecommendation).where(
            RecoveryRecommendation.case_id == case_id,
            RecoveryRecommendation.analysis_run_id == run_id,
        )
    ).scalars().all()
    assert rows
    assert any(
        factor.get("code") == "ACTIVE_RAIL_DOWNTIME"
        for row in rows
        for factor in row.factors
    )
    assert client.captured_downtime["downtime"].lookup_status == "KNOWN"  # type: ignore[attr-defined]
    assert client.captured_downtime["downtime"].rail_degraded is True  # type: ignore[attr-defined]


def test_analyze_missing_credentials_unknown_downtime_without_provider_http(
    seeded_database,
    api_demo_settings,
    analyzable_case,
    fresh_db_session,
    monkeypatch,
) -> None:
    txn = fresh_db_session.get(Transaction, analyzable_case.transaction_id)
    assert txn is not None
    txn.payment_method = "upi"
    txn.last_provider_event_at = FAILURE_AT
    fresh_db_session.commit()
    case_id = analyzable_case.id

    blank_settings = api_demo_settings.model_copy(
        update={
            "razorpay_key_id": SecretStr(""),
            "razorpay_key_secret": SecretStr(""),
        }
    )

    def forbidden_create_read_client(*_args, **_kwargs):
        raise AssertionError("provider HTTP client must not be created without credentials")

    monkeypatch.setattr(
        "app.integrations.razorpay.provider.create_razorpay_read_client",
        forbidden_create_read_client,
    )

    client = _build_client(
        seeded_database=seeded_database,
        settings=blank_settings,
        monkeypatch=monkeypatch,
    )
    response = client.post(
        f"/api/v1/recovery-cases/{case_id}/analyze",
        headers=DEMO_AUTH_HEADERS,
        json={"reason": "MANUAL_ANALYSIS"},
    )
    assert response.status_code == 200
    downtime = client.captured_downtime["downtime"]  # type: ignore[attr-defined]
    assert downtime.lookup_status == "UNKNOWN"
    assert downtime.severity == "unknown"
    assert downtime.rail_degraded is False

    run_id = UUID(response.json()["analysis_run_id"])
    rows = fresh_db_session.execute(
        select(RecoveryRecommendation).where(
            RecoveryRecommendation.case_id == case_id,
            RecoveryRecommendation.analysis_run_id == run_id,
        )
    ).scalars().all()
    assert rows
    assert not any(
        factor.get("code") == "ACTIVE_RAIL_DOWNTIME"
        for row in rows
        for factor in row.factors
    )
