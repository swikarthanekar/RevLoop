"""Which APP_ENV / DEMO_MODE combination a deployed demo can actually use.

`DEMO_MODE` decides whether the demo routes are registered at all, and `APP_ENV`
independently decides which authentication backend resolves the bearer token.
The two are not the same switch, and only one combination produces a demo that
can authenticate today. These tests pin that so a deployment configuration
change cannot quietly turn the demo into a 501, and so the reason is recorded
next to the code rather than only in deployment notes.

No database is required: the auth decision happens before any route runs.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.core.auth import DevAuthBackend, SupabaseAuthBackend, get_auth_backend
from app.core.config import Settings
from app.domain.enums import UserRole

DEMO_USER_ID = "e4546079-9319-5bdb-965c-339a38ea4f34"
DEMO_ORGANIZATION_ID = "82757dbc-e0d0-5285-8f26-7a9ab9837a24"

#: Non-"dev-" placeholders, required for Settings to build in production.
PRODUCTION_PLACEHOLDERS = {
    "supabase_jwt_secret": "placeholder-supabase-jwt-secret",
    "razorpay_key_id": "placeholder-key-id",
    "razorpay_key_secret": "placeholder-key-secret",
    "razorpay_webhook_secret": "placeholder-webhook-secret",
}


def development_settings(**overrides) -> Settings:
    values = {
        "app_env": "development",
        "demo_mode": True,
        "dev_auth_user_id": DEMO_USER_ID,
        "dev_auth_organization_id": DEMO_ORGANIZATION_ID,
        **overrides,
    }
    return Settings(_env_file=None, **values)


def production_settings(**overrides) -> Settings:
    values = {"app_env": "production", **PRODUCTION_PLACEHOLDERS, **overrides}
    return Settings(_env_file=None, **values)


def test_app_env_accepts_only_development_test_and_production() -> None:
    """There is no `demo` environment; a demo deployment is not its own APP_ENV."""
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="demo")


def test_development_app_env_selects_the_development_backend() -> None:
    assert isinstance(get_auth_backend(development_settings()), DevAuthBackend)


def test_production_app_env_selects_the_supabase_backend() -> None:
    assert isinstance(get_auth_backend(production_settings()), SupabaseAuthBackend)


def test_development_app_env_resolves_the_demo_admin_identity() -> None:
    """ADMIN is what the demo reset endpoint requires."""
    context = get_auth_backend(development_settings()).resolve("dev-admin")

    assert context.role == UserRole.ADMIN
    assert str(context.organization_id) == DEMO_ORGANIZATION_ID


def test_production_app_env_cannot_authenticate_any_token_yet() -> None:
    """Supabase JWT verification is unimplemented, so production auth is 501.

    A demo deployed with APP_ENV=production therefore cannot reach POST
    /api/v1/demo/reset — or any authenticated route — regardless of DEMO_MODE.
    """
    backend = get_auth_backend(production_settings())

    with pytest.raises(HTTPException) as excinfo:
        backend.resolve("dev-admin")

    assert excinfo.value.status_code == 501
    assert excinfo.value.detail["code"] == "AUTH_NOT_CONFIGURED"


def test_demo_mode_is_configurable_independently_of_app_env() -> None:
    """DEMO_MODE only registers routes; it is not the production safety gate.

    Settings accepts demo_mode=True in production, so the protection that keeps
    a deployed demo safe is the ADMIN authorization on the route plus the auth
    backend selection above — not the flag on its own.
    """
    assert production_settings(demo_mode=True).demo_mode is True
    assert development_settings(demo_mode=False).demo_mode is False


def test_development_auth_without_configured_ids_refuses_to_grant_a_role() -> None:
    """A missing DEV_AUTH_* pair fails closed rather than defaulting a tenant."""
    settings = Settings(_env_file=None, app_env="development", demo_mode=True)

    with pytest.raises(HTTPException) as excinfo:
        DevAuthBackend(settings).resolve("dev-admin")

    assert excinfo.value.status_code == 503
    assert excinfo.value.detail["code"] == "AUTH_NOT_CONFIGURED"


def test_production_pins_the_canonical_razorpay_host() -> None:
    """The Prompt 25 local provider stub override cannot follow into production."""
    assert production_settings().razorpay_api_base_url == "https://api.razorpay.com"

    with pytest.raises(ValidationError):
        production_settings(razorpay_api_base_url="http://localhost:8787")
