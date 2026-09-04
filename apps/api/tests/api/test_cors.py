"""Browser origin access to the API.

The frontend is a separate origin that calls this API directly from the browser,
so without CORS headers every request fails at the network layer and the app
renders "Unable to reach the RevLoop API". Only the configured public app origin
is allowed.

CORS is configured when the app is built, so these tests set the environment and
clear the settings cache before calling `create_app`.
"""

from __future__ import annotations

from collections.abc import Callable, Generator

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app

ALLOWED_ORIGIN = "http://localhost:3100"
FOREIGN_ORIGIN = "http://evil.example.com"


ClientFactory = Callable[..., TestClient]


@pytest.fixture
def build_client(monkeypatch: pytest.MonkeyPatch) -> Generator[ClientFactory, None, None]:
    def factory(public_app_base_url: str = ALLOWED_ORIGIN) -> TestClient:
        monkeypatch.setenv("APP_ENV", "test")
        monkeypatch.setenv("PUBLIC_APP_BASE_URL", public_app_base_url)
        get_settings.cache_clear()
        return TestClient(create_app(), raise_server_exceptions=False)

    yield factory
    # Drop the cached settings built from the patched environment.
    get_settings.cache_clear()


def test_preflight_from_the_configured_app_origin_is_allowed(build_client) -> None:
    response = build_client().options(
        "/api/v1/dashboard/summary",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


def test_simple_request_from_the_app_origin_carries_allow_origin(build_client) -> None:
    response = build_client().get("/health", headers={"Origin": ALLOWED_ORIGIN})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN


def test_a_trailing_slash_in_configuration_still_matches_the_browser_origin(
    build_client,
) -> None:
    """Browsers send an origin with no trailing slash."""
    response = build_client(f"{ALLOWED_ORIGIN}/").get(
        "/health", headers={"Origin": ALLOWED_ORIGIN}
    )

    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN


def test_an_https_deployment_origin_is_allowed(build_client) -> None:
    """The deployed frontend is an https origin on a hosting domain."""
    origin = "https://revloop-example.vercel.app"
    response = build_client(origin).get("/health", headers={"Origin": origin})

    assert response.headers["access-control-allow-origin"] == origin


def test_no_wildcard_origin_is_ever_advertised(build_client) -> None:
    response = build_client().get("/health", headers={"Origin": ALLOWED_ORIGIN})

    assert response.headers.get("access-control-allow-origin") != "*"


def test_foreign_origin_is_not_granted_access(build_client) -> None:
    response = build_client().get("/health", headers={"Origin": FOREIGN_ORIGIN})

    # The request still succeeds server-side; the browser is denied because no
    # allow-origin header is returned for the foreign origin.
    assert response.headers.get("access-control-allow-origin") != FOREIGN_ORIGIN


def test_credentials_are_not_allowed_cross_origin(build_client) -> None:
    """Auth travels as a Bearer header, so cookie credentials stay disabled."""
    response = build_client().get("/health", headers={"Origin": ALLOWED_ORIGIN})

    assert "access-control-allow-credentials" not in response.headers
