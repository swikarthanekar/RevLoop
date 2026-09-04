"""GET /api/v1/policies — read-only compliance guardrails."""

from __future__ import annotations

from app.demo.constants import (
    ALLOWED_ACTION_TYPES,
    AUTO_ACTION_LIMIT_MINOR,
)
from tests.api.conftest import DEMO_AUTH_HEADERS


def test_policy_requires_auth(api_client) -> None:
    response = api_client.get("/api/v1/policies")
    assert response.status_code == 401


def test_policy_reflects_the_seeded_merchant_policy(api_client) -> None:
    response = api_client.get("/api/v1/policies", headers=DEMO_AUTH_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["currency"] == "INR"
    assert body["auto_action_limit_minor"] == AUTO_ACTION_LIMIT_MINOR
    assert sorted(body["allowed_action_types"]) == sorted(ALLOWED_ACTION_TYPES)
    assert "ESCALATE_TO_HUMAN" in body["manual_contact_approval_action_types"]
    assert isinstance(body["automation_enabled"], bool)
    assert 0 <= body["minimum_auto_confidence"] <= 1


def test_policy_tenant_isolation(api_client, other_org_client) -> None:
    """A different organization's policy is never returned to this tenant."""
    own = api_client.get("/api/v1/policies", headers=DEMO_AUTH_HEADERS)
    other = other_org_client.get("/api/v1/policies")

    assert own.status_code == 200
    # The other-org client is scoped to an organization with no seeded
    # policy row -- proves this route never falls back to another tenant's
    # configuration.
    assert other.status_code == 404
    assert other.json()["error"]["code"] == "POLICY_NOT_FOUND"
