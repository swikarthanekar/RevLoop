"""Recovery case list API tests."""

from __future__ import annotations

import uuid

from app.demo.constants import DEMO_CASE_UPI_DOWNTIME_ID
from app.domain.enums import RecoveryCaseStatus
from tests.api.conftest import DEMO_AUTH_HEADERS


def test_list_recovery_cases_requires_auth(api_client) -> None:
    response = api_client.get("/api/v1/recovery-cases")
    assert response.status_code == 401


def test_list_recovery_cases_pagination(api_client) -> None:
    first_page = api_client.get(
        "/api/v1/recovery-cases",
        headers=DEMO_AUTH_HEADERS,
        params={"limit": 10, "offset": 0},
    )
    second_page = api_client.get(
        "/api/v1/recovery-cases",
        headers=DEMO_AUTH_HEADERS,
        params={"limit": 10, "offset": 10},
    )

    assert first_page.status_code == 200
    assert second_page.status_code == 200
    first_payload = first_page.json()
    second_payload = second_page.json()

    assert first_payload["limit"] == 10
    assert first_payload["offset"] == 0
    assert len(first_payload["items"]) == 10
    assert first_payload["total"] >= 100
    first_ids = {item["id"] for item in first_payload["items"]}
    second_ids = {item["id"] for item in second_payload["items"]}
    assert first_ids.isdisjoint(second_ids)


def test_list_recovery_cases_status_filter(api_client) -> None:
    response = api_client.get(
        "/api/v1/recovery-cases",
        headers=DEMO_AUTH_HEADERS,
        params={"status": RecoveryCaseStatus.RECOMMENDED.value, "limit": 100},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 1
    assert all(item["status"] == RecoveryCaseStatus.RECOMMENDED.value for item in payload["items"])


def test_list_recovery_cases_comma_status_filter(api_client) -> None:
    statuses = f"{RecoveryCaseStatus.RECOVERED.value},{RecoveryCaseStatus.FAILED.value}"
    response = api_client.get(
        "/api/v1/recovery-cases",
        headers=DEMO_AUTH_HEADERS,
        params={"status": statuses, "limit": 100},
    )
    assert response.status_code == 200
    allowed = {RecoveryCaseStatus.RECOVERED.value, RecoveryCaseStatus.FAILED.value}
    assert all(item["status"] in allowed for item in response.json()["items"])


def test_list_recovery_cases_sort_amount_desc(api_client) -> None:
    response = api_client.get(
        "/api/v1/recovery-cases",
        headers=DEMO_AUTH_HEADERS,
        params={"sort": "amount_desc", "limit": 5},
    )
    assert response.status_code == 200
    amounts = [item["amount_at_risk_minor"] for item in response.json()["items"]]
    assert amounts == sorted(amounts, reverse=True)


def test_list_recovery_cases_includes_recommendation_fields(api_client) -> None:
    response = api_client.get(
        "/api/v1/recovery-cases",
        headers=DEMO_AUTH_HEADERS,
        params={"limit": 100},
    )
    assert response.status_code == 200
    upi_case = next(
        item for item in response.json()["items"] if item["id"] == str(DEMO_CASE_UPI_DOWNTIME_ID)
    )
    assert upi_case["recommended_action"] is not None
    assert upi_case["confidence"] is not None


def test_list_recovery_cases_invalid_limit(api_client) -> None:
    response = api_client.get(
        "/api/v1/recovery-cases",
        headers=DEMO_AUTH_HEADERS,
        params={"limit": 101},
    )
    assert response.status_code == 422


def test_list_recovery_cases_invalid_offset(api_client) -> None:
    response = api_client.get(
        "/api/v1/recovery-cases",
        headers=DEMO_AUTH_HEADERS,
        params={"offset": -1},
    )
    assert response.status_code == 422


def test_list_recovery_cases_invalid_sort(api_client) -> None:
    response = api_client.get(
        "/api/v1/recovery-cases",
        headers=DEMO_AUTH_HEADERS,
        params={"sort": "invalid_sort"},
    )
    assert response.status_code == 422


def test_list_recovery_cases_invalid_amount_range(api_client) -> None:
    response = api_client.get(
        "/api/v1/recovery-cases",
        headers=DEMO_AUTH_HEADERS,
        params={"min_amount_minor": 500000, "max_amount_minor": 100000},
    )
    assert response.status_code == 422


def test_list_recovery_cases_tenant_isolation(api_client, other_org_client) -> None:
    demo_response = api_client.get(
        "/api/v1/recovery-cases",
        headers=DEMO_AUTH_HEADERS,
        params={"limit": 5},
    )
    other_response = other_org_client.get(
        "/api/v1/recovery-cases",
        headers=DEMO_AUTH_HEADERS,
        params={"limit": 5},
    )

    assert demo_response.status_code == 200
    assert other_response.status_code == 200
    assert demo_response.json()["total"] > 0
    assert other_response.json()["total"] == 0
    assert other_response.json()["items"] == []


def test_list_recovery_cases_unknown_id_filter_returns_empty(api_client) -> None:
    response = api_client.get(
        "/api/v1/recovery-cases",
        headers=DEMO_AUTH_HEADERS,
        params={"customer_id": str(uuid.uuid4())},
    )
    assert response.status_code == 200
    assert response.json()["total"] == 0
