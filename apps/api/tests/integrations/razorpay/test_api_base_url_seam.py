"""Provider base URL configuration seam.

Automated tests need the real RazorpayClient to talk to a local stub instead of
the live provider. That override is only legitimate outside production, so the
canonical host is pinned whenever APP_ENV=production.
"""

from __future__ import annotations

import httpx
import pytest

from app.core.config import RAZORPAY_DEFAULT_API_BASE_URL, Settings
from app.integrations.razorpay.client import RazorpayClient

LOCAL_STUB_URL = "http://127.0.0.1:8200"

# Syntactically valid, obviously fake test credentials. They exist purely so the
# production configuration checks pass against a local stub.
TEST_KEY_ID = "rzp_test_e2elocalstub"
TEST_KEY_SECRET = "e2elocalstubsecret"


def build_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "app_env": "test",
        "razorpay_key_id": TEST_KEY_ID,
        "razorpay_key_secret": TEST_KEY_SECRET,
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


def test_default_base_url_is_the_canonical_razorpay_host() -> None:
    assert build_settings().razorpay_api_base_url == RAZORPAY_DEFAULT_API_BASE_URL
    assert RAZORPAY_DEFAULT_API_BASE_URL == "https://api.razorpay.com"


def test_missing_override_preserves_existing_client_behaviour() -> None:
    client = RazorpayClient.from_settings(build_settings())
    assert str(client._client.base_url) == RAZORPAY_DEFAULT_API_BASE_URL


def test_non_production_may_point_the_client_at_a_local_stub() -> None:
    settings = build_settings(razorpay_api_base_url=LOCAL_STUB_URL)
    client = RazorpayClient.from_settings(settings)

    assert str(client._client.base_url) == LOCAL_STUB_URL


def test_development_may_also_override_the_base_url() -> None:
    settings = build_settings(app_env="development", razorpay_api_base_url=LOCAL_STUB_URL)

    assert settings.razorpay_api_base_url == LOCAL_STUB_URL


def test_production_rejects_a_local_provider_override() -> None:
    with pytest.raises(ValueError, match="canonical Razorpay API base URL"):
        Settings(
            _env_file=None,
            app_env="production",
            supabase_jwt_secret="real-jwt-secret",
            razorpay_key_id="rzp_live_real",
            razorpay_key_secret="real-secret",
            razorpay_webhook_secret="real-webhook-secret",
            razorpay_api_base_url=LOCAL_STUB_URL,
        )


def test_production_accepts_the_canonical_base_url() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        supabase_jwt_secret="real-jwt-secret",
        razorpay_key_id="rzp_live_real",
        razorpay_key_secret="real-secret",
        razorpay_webhook_secret="real-webhook-secret",
        razorpay_api_base_url=RAZORPAY_DEFAULT_API_BASE_URL,
    )

    assert settings.razorpay_api_base_url == RAZORPAY_DEFAULT_API_BASE_URL


def test_the_overridden_host_is_actually_used_for_requests() -> None:
    """The override must change where the real client sends its payment link POST."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"id": "plink_stub", "reference_id": "rl_x"})

    settings = build_settings(razorpay_api_base_url=LOCAL_STUB_URL)
    client = RazorpayClient.from_settings(settings, transport=httpx.MockTransport(handler))
    client.post_json(client.get_payment_links_path(), {"amount": 1})

    assert str(seen[0].url) == f"{LOCAL_STUB_URL}/v1/payment_links"
