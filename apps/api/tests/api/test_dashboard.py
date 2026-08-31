"""Dashboard summary API tests."""

from __future__ import annotations

from app.demo.constants import DEMO_SOURCE_LABEL
from app.demo.summary import summary_from_database
from tests.api.conftest import DEMO_AUTH_HEADERS


def test_dashboard_summary_requires_auth(api_client) -> None:
    response = api_client.get("/api/v1/dashboard/summary")
    assert response.status_code == 401


def test_dashboard_summary_matches_seeded_aggregates(api_client, db_session) -> None:
    seed_summary = summary_from_database(db_session)

    response = api_client.get("/api/v1/dashboard/summary", headers=DEMO_AUTH_HEADERS)
    assert response.status_code == 200
    payload = response.json()

    assert payload["currency"] == "INR"
    assert payload["active_cases"] == seed_summary.active_cases
    assert payload["recovered_cases"] == seed_summary.recovered_cases
    assert payload["revenue_at_risk_minor"] == seed_summary.open_revenue_at_risk_minor
    assert payload["revenue_recovered_minor"] == seed_summary.historical_recovered_revenue_minor
    assert payload["source_label"] == DEMO_SOURCE_LABEL
    assert payload["incremental_recovered_minor"] == max(
        0,
        payload["revenue_recovered_minor"] - payload["baseline_recovered_minor"],
    )
    assert 0.0 <= payload["recovery_rate"] <= 1.0
    assert isinstance(payload["recovery_trend"], list)
    assert isinstance(payload["action_effectiveness"], list)
    assert isinstance(payload["failure_breakdown"], list)
    assert len(payload["failure_breakdown"]) > 0


def test_dashboard_summary_empty_organization(empty_org_client) -> None:
    response = empty_org_client.get("/api/v1/dashboard/summary", headers=DEMO_AUTH_HEADERS)
    assert response.status_code == 200
    payload = response.json()

    assert payload["active_cases"] == 0
    assert payload["recovered_cases"] == 0
    assert payload["revenue_at_risk_minor"] == 0
    assert payload["revenue_recovered_minor"] == 0
    assert payload["baseline_recovered_minor"] == 0
    assert payload["incremental_recovered_minor"] == 0
    assert payload["recovery_rate"] == 0.0
    assert payload["recovery_trend"] == []
    assert payload["action_effectiveness"] == []
    assert payload["failure_breakdown"] == []


def test_dashboard_summary_rejects_invalid_date_range(api_client) -> None:
    response = api_client.get(
        "/api/v1/dashboard/summary",
        headers=DEMO_AUTH_HEADERS,
        params={"from": "2026-08-30T00:00:00Z", "to": "2026-08-01T00:00:00Z"},
    )
    assert response.status_code == 422


def test_dashboard_summary_tenant_isolation(api_client, other_org_client) -> None:
    demo_response = api_client.get("/api/v1/dashboard/summary", headers=DEMO_AUTH_HEADERS)
    other_response = other_org_client.get("/api/v1/dashboard/summary", headers=DEMO_AUTH_HEADERS)

    assert demo_response.status_code == 200
    assert other_response.status_code == 200
    assert demo_response.json()["active_cases"] > 0
    assert other_response.json()["active_cases"] == 0


def test_dashboard_synthetic_source_filter(api_client, db_session) -> None:
    response = api_client.get(
        "/api/v1/dashboard/summary",
        headers=DEMO_AUTH_HEADERS,
        params={"source": "synthetic"},
    )
    assert response.status_code == 200
    full = api_client.get("/api/v1/dashboard/summary", headers=DEMO_AUTH_HEADERS).json()
    filtered = response.json()
    assert filtered["active_cases"] == full["active_cases"]
    assert filtered["source_label"] == DEMO_SOURCE_LABEL


def test_dashboard_average_recovery_seconds(api_client) -> None:
    response = api_client.get("/api/v1/dashboard/summary", headers=DEMO_AUTH_HEADERS)
    assert response.status_code == 200
    assert response.json()["average_recovery_seconds"] is not None
