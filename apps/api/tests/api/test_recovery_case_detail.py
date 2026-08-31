"""Recovery case detail API tests."""

from __future__ import annotations

import uuid

from app.demo.constants import (
    DEMO_CASE_HIGH_VALUE_APPROVAL_ID,
    DEMO_CASE_RECOVERED_HISTORY_ID,
    DEMO_CASE_UPI_DOWNTIME_ID,
)
from app.domain.enums import RecoveryCaseStatus
from tests.api.conftest import DEMO_AUTH_HEADERS


def test_get_recovery_case_detail_success(api_client) -> None:
    response = api_client.get(
        f"/api/v1/recovery-cases/{DEMO_CASE_UPI_DOWNTIME_ID}",
        headers=DEMO_AUTH_HEADERS,
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["case"]["id"] == str(DEMO_CASE_UPI_DOWNTIME_ID)
    assert payload["case"]["status"] == RecoveryCaseStatus.RECOMMENDED.value
    assert payload["case"]["amount_at_risk_minor"] == 499900
    assert payload["customer"]["display_name"]
    assert payload["source"]["type"] == "TRANSACTION"
    assert payload["analysis"] is not None
    assert payload["analysis"]["selected_action"]
    assert payload["analysis"]["structured_explanation"]["summary"]


def test_get_recovery_case_detail_recovered_history(api_client) -> None:
    response = api_client.get(
        f"/api/v1/recovery-cases/{DEMO_CASE_RECOVERED_HISTORY_ID}",
        headers=DEMO_AUTH_HEADERS,
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["case"]["status"] == RecoveryCaseStatus.RECOVERED.value
    assert payload["source"]["type"] == "SUBSCRIPTION"
    assert payload["latest_action"] is not None
    assert payload["outcome"] is not None
    assert payload["outcome"]["outcome"] == "RECOVERED"


def test_get_recovery_case_detail_awaiting_approval(api_client) -> None:
    response = api_client.get(
        f"/api/v1/recovery-cases/{DEMO_CASE_HIGH_VALUE_APPROVAL_ID}",
        headers=DEMO_AUTH_HEADERS,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["case"]["status"] == RecoveryCaseStatus.AWAITING_APPROVAL.value
    assert payload["case"]["amount_at_risk_minor"] == 3_500_000


def test_get_recovery_case_unknown_id_returns_404(api_client) -> None:
    response = api_client.get(
        f"/api/v1/recovery-cases/{uuid.uuid4()}",
        headers=DEMO_AUTH_HEADERS,
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CASE_NOT_FOUND"


def test_get_recovery_case_other_tenant_returns_403(other_org_client) -> None:
    response = other_org_client.get(
        f"/api/v1/recovery-cases/{DEMO_CASE_UPI_DOWNTIME_ID}",
        headers=DEMO_AUTH_HEADERS,
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "TENANT_ACCESS_DENIED"
