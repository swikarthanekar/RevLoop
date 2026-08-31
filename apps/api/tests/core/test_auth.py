from pathlib import Path
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.auth import DevAuthBackend
from app.core.config import Settings, get_settings
from app.domain.enums import UserRole

DEV_AUTH_USER_ID = UUID("00000000-0000-4000-8000-000000000001")
DEV_AUTH_ORG_ID = UUID("00000000-0000-4000-8000-000000000010")


@pytest.fixture(autouse=True)
def configure_dev_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEV_AUTH_USER_ID", str(DEV_AUTH_USER_ID))
    monkeypatch.setenv("DEV_AUTH_ORGANIZATION_ID", str(DEV_AUTH_ORG_ID))
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_auth_module_does_not_import_demo_packages() -> None:
    source = Path(__file__).resolve().parents[2] / "app" / "core" / "auth.py"
    contents = source.read_text(encoding="utf-8")
    assert "app.demo" not in contents


def test_dev_auth_resolves_role_from_bearer_token(client_with_test_routes: TestClient) -> None:
    response = client_with_test_routes.get(
        "/_test/me",
        headers={"Authorization": "Bearer dev-admin"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["role"] == UserRole.ADMIN.value
    assert payload["organization_id"] == str(DEV_AUTH_ORG_ID)
    assert payload["user_id"] == str(DEV_AUTH_USER_ID)


def test_auth_context_organization_id_comes_from_settings() -> None:
    settings = Settings(
        _env_file=None,
        app_env="development",
        dev_auth_user_id=DEV_AUTH_USER_ID,
        dev_auth_organization_id=DEV_AUTH_ORG_ID,
    )
    backend = DevAuthBackend(settings)
    context = backend.resolve("dev-analyst")

    assert context.organization_id == settings.dev_auth_organization_id
    assert context.user_id == settings.dev_auth_user_id
    assert context.role == UserRole.ANALYST


def test_auth_context_is_not_sourced_from_request_body_organization_id() -> None:
    settings = Settings(
        _env_file=None,
        app_env="development",
        dev_auth_user_id=DEV_AUTH_USER_ID,
        dev_auth_organization_id=DEV_AUTH_ORG_ID,
    )
    backend = DevAuthBackend(settings)
    context = backend.resolve("dev-analyst")

    assert context.organization_id == DEV_AUTH_ORG_ID
    assert context.user_id == DEV_AUTH_USER_ID
    assert context.role == UserRole.ANALYST


@pytest.mark.parametrize(
    ("token", "expected_role"),
    [
        ("dev-analyst", UserRole.ANALYST),
        ("dev-operator", UserRole.OPERATOR),
        ("dev-admin", UserRole.ADMIN),
    ],
)
def test_dev_tokens_resolve_expected_roles(token: str, expected_role: UserRole) -> None:
    settings = Settings(
        _env_file=None,
        app_env="development",
        dev_auth_user_id=DEV_AUTH_USER_ID,
        dev_auth_organization_id=DEV_AUTH_ORG_ID,
    )
    context = DevAuthBackend(settings).resolve(token)
    assert context.role == expected_role


def test_missing_dev_auth_configuration_fails_clearly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEV_AUTH_USER_ID", raising=False)
    monkeypatch.delenv("DEV_AUTH_ORGANIZATION_ID", raising=False)
    get_settings.cache_clear()

    settings = Settings(_env_file=None, app_env="development")
    backend = DevAuthBackend(settings)

    with pytest.raises(HTTPException) as exc_info:
        backend.resolve("dev-analyst")

    assert exc_info.value.status_code == 503
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["code"] == "AUTH_NOT_CONFIGURED"
    assert "DEV_AUTH_USER_ID" in detail["message"]
    assert "DEV_AUTH_ORGANIZATION_ID" in detail["message"]


def test_missing_auth_token_returns_unauthorized(client_with_test_routes: TestClient) -> None:
    response = client_with_test_routes.get("/_test/me")

    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "UNAUTHORIZED"
