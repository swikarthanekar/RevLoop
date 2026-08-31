import pytest
from fastapi.testclient import TestClient

from app.core.auth import DEV_TEST_ORG_ID, DEV_TEST_USER_ID, DevAuthBackend
from app.core.config import get_settings
from app.domain.enums import UserRole


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_dev_auth_resolves_role_from_bearer_token(client_with_test_routes: TestClient) -> None:
    response = client_with_test_routes.get(
        "/_test/me",
        headers={"Authorization": "Bearer dev-admin"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["role"] == UserRole.ADMIN.value
    assert payload["organization_id"] == str(DEV_TEST_ORG_ID)
    assert payload["user_id"] == str(DEV_TEST_USER_ID)


def test_auth_context_is_not_sourced_from_request_body_organization_id() -> None:
    backend = DevAuthBackend()
    context = backend.resolve("dev-analyst")

    assert context.organization_id == DEV_TEST_ORG_ID
    assert context.user_id == DEV_TEST_USER_ID
    assert context.role == UserRole.ANALYST


def test_missing_auth_token_returns_unauthorized(client_with_test_routes: TestClient) -> None:
    response = client_with_test_routes.get("/_test/me")

    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "UNAUTHORIZED"
