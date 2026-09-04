"""GET /api/v1/auth/me — authenticated-identity read route."""

from __future__ import annotations

from app.demo.constants import DEMO_AUTH_USER_ANALYST_ID, DEMO_ORGANIZATION_ID
from tests.api.conftest import DEMO_AUTH_HEADERS


def test_me_requires_auth(api_client) -> None:
    response = api_client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_me_resolves_the_bearer_token_identity(api_client) -> None:
    response = api_client.get("/api/v1/auth/me", headers=DEMO_AUTH_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == str(DEMO_AUTH_USER_ANALYST_ID)
    assert body["organization_id"] == str(DEMO_ORGANIZATION_ID)
    assert body["role"] == "ANALYST"


def test_me_reflects_role_from_the_token(api_client) -> None:
    response = api_client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer dev-admin"}
    )

    assert response.status_code == 200
    assert response.json()["role"] == "ADMIN"
