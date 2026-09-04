"""Which APP_ENV / DEMO_MODE combination a deployed demo can actually use.

`DEMO_MODE` decides whether the demo routes are registered at all, and `APP_ENV`
independently decides which authentication backend resolves the bearer token.
The two are not the same switch: development selects DevAuthBackend (fixed
DEV_AUTH_* identity), production selects SupabaseAuthBackend (real JWT
verification against a provisioned user_profiles row). These tests pin the
selection and the development backend's own failure modes so a deployment
configuration change cannot quietly select the wrong backend. SupabaseAuthBackend's
own JWT-verification behavior (valid/expired/wrong-secret/wrong-audience/no
matching profile) is covered separately in tests/core/test_supabase_auth.py,
since it requires a database.

No database is required for the tests in this file: they exercise selection
and the paths that fail before any database lookup would happen.
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


def test_production_app_env_rejects_a_non_jwt_token() -> None:
    """SupabaseAuthBackend verifies a real Supabase-issued JWT; the
    development bearer tokens ("dev-admin" etc.) are not valid JWTs and are
    rejected the same way any malformed token is -- 401, not the old 501
    stub. (No database needed: JWT decoding fails before any lookup.)
    """
    backend = get_auth_backend(production_settings())

    with pytest.raises(HTTPException) as excinfo:
        backend.resolve("dev-admin")

    assert excinfo.value.status_code == 401
    assert excinfo.value.detail["code"] == "UNAUTHORIZED"


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
