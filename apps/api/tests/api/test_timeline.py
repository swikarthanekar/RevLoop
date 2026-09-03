"""Recovery case timeline API tests."""

from __future__ import annotations

import uuid

from app.demo.constants import DEMO_CASE_RECOVERED_HISTORY_ID, DEMO_CASE_UPI_DOWNTIME_ID
from tests.api.conftest import DEMO_AUTH_HEADERS


def test_timeline_requires_auth(api_client) -> None:
    response = api_client.get(f"/api/v1/recovery-cases/{DEMO_CASE_UPI_DOWNTIME_ID}/timeline")
    assert response.status_code == 401


def test_timeline_returns_chronological_entries(api_client) -> None:
    response = api_client.get(
        f"/api/v1/recovery-cases/{DEMO_CASE_UPI_DOWNTIME_ID}/timeline",
        headers=DEMO_AUTH_HEADERS,
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) >= 2
    timestamps = [item["occurred_at"] for item in items]
    assert timestamps == sorted(timestamps)
    assert items[0]["event_type"] == "CASE_CREATED"
    assert "occurred_at" in items[0]
    assert "summary" in items[0]


def test_timeline_recovered_history_has_extended_events(api_client) -> None:
    response = api_client.get(
        f"/api/v1/recovery-cases/{DEMO_CASE_RECOVERED_HISTORY_ID}/timeline",
        headers=DEMO_AUTH_HEADERS,
    )
    assert response.status_code == 200
    event_types = [item["event_type"] for item in response.json()["items"]]
    assert "OUTCOME_VERIFIED" in event_types


def test_timeline_filters_sensitive_evidence(api_client, db_session) -> None:
    """Evidence is projected through a fail-closed allowlist.

    This previously asserted that a nested mapping survived with its "safe"
    members intact, which encoded the old denylist behaviour. Arbitrary nested
    structure is no longer published at all; see
    ``tests/api/test_timeline_security.py`` for the full sentinel regression.
    """
    from app.demo.constants import DEMO_ORGANIZATION_ID
    from app.domain.enums import AuditActorType
    from app.models.audit_log import AuditLog

    case_id = DEMO_CASE_UPI_DOWNTIME_ID
    entry = AuditLog(
        organization_id=DEMO_ORGANIZATION_ID,
        case_id=case_id,
        actor_type=AuditActorType.SYSTEM.value,
        actor_id="test",
        event_type="TEST_SENSITIVE",
        summary="Sensitive evidence test event.",
        evidence={
            "provider_event_id": "evt_safe_123",
            "authorization": "Bearer secret-token",
            "email": "secret@example.com",
            "nested": {"api_key": "abc", "safe_field": "visible"},
        },
    )
    db_session.add(entry)
    db_session.commit()

    try:
        response = api_client.get(
            f"/api/v1/recovery-cases/{case_id}/timeline",
            headers=DEMO_AUTH_HEADERS,
        )
        assert response.status_code == 200
        sensitive = next(
            item for item in response.json()["items"] if item["event_type"] == "TEST_SENSITIVE"
        )
        evidence = sensitive["evidence"]

        # The one allowlisted, correctly shaped field survives.
        assert evidence == {"provider_event_id": "evt_safe_123"}
        assert "authorization" not in evidence
        assert "email" not in evidence
        # Arbitrary nested structure is dropped entirely, not recursed into.
        assert "nested" not in evidence
        assert "visible" not in response.text
        assert "secret@example.com" not in response.text
    finally:
        db_session.delete(entry)
        db_session.commit()


def test_timeline_unknown_case_returns_404(api_client) -> None:
    response = api_client.get(
        f"/api/v1/recovery-cases/{uuid.uuid4()}/timeline",
        headers=DEMO_AUTH_HEADERS,
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CASE_NOT_FOUND"


def test_timeline_other_tenant_returns_403(other_org_client) -> None:
    response = other_org_client.get(
        f"/api/v1/recovery-cases/{DEMO_CASE_UPI_DOWNTIME_ID}/timeline",
        headers=DEMO_AUTH_HEADERS,
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "TENANT_ACCESS_DENIED"
