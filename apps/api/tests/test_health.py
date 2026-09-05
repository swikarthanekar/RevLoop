from contextlib import contextmanager
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.core.config import get_settings
from app.main import app

client = TestClient(app)


@contextmanager
def _reachable_database():
    """Stand in for a working session factory.

    The rest of the suite skips database-backed tests unless
    `REVLOOP_TEST_DATABASE_URL` points at a reachable Postgres, so the health
    contract is asserted against a stub instead: the route's behaviour, not the
    database, is what is under test here.
    """

    class _Session:
        def execute(self, _statement: object) -> None:
            return None

        def __enter__(self) -> "_Session":
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

    with patch("app.api.routes.health.get_session_factory", lambda _settings: _Session):
        yield


def test_application_import_smoke() -> None:
    from app.main import app as imported_app

    assert imported_app.title == "RevLoop API"


def test_health_returns_contract_shape() -> None:
    settings = get_settings()
    with _reachable_database():
        response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "status": "ok",
        "database": "ok",
        "model": "loaded" if settings.model_bundle_path.exists() else "not_loaded",
        "version": settings.api_version,
    }


def test_health_reports_an_unreachable_database_without_failing() -> None:
    """A database outage degrades one field; it must not fail the route.

    Railway probes `/health`, so a 500 or a 503 here would let a transient
    database problem restart or fail-deploy a container that is still serving.
    """

    def _raise(_settings: object) -> None:
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    with patch("app.api.routes.health.get_session_factory", _raise):
        response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["database"] == "unavailable"
    # The process is still up, so the top-level status stays "ok".
    assert payload["status"] == "ok"


def test_production_app_has_no_test_routes() -> None:
    paths = app.openapi()["paths"]
    assert not any("/_test" in path for path in paths)


def test_production_app_has_no_skeleton_routes() -> None:
    paths = app.openapi()["paths"]
    assert not any("_skeleton" in path for path in paths)


def test_api_v1_router_is_available() -> None:
    response = client.get("/api/v1")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "v1"}


def test_registered_api_v1_routes_after_cleanup() -> None:
    api_v1_paths = sorted(path for path in app.openapi()["paths"] if path.startswith("/api/v1"))
    expected = [
        "/api/v1/",
        "/api/v1/auth/me",
        "/api/v1/dashboard/summary",
        "/api/v1/policies",
        "/api/v1/provider-events",
        "/api/v1/recovery-actions/{action_id}/approve",
        "/api/v1/recovery-actions/{action_id}/reject",
        "/api/v1/recovery-cases",
        "/api/v1/recovery-cases/{case_id}",
        "/api/v1/recovery-cases/{case_id}/actions",
        "/api/v1/recovery-cases/{case_id}/analyze",
        "/api/v1/recovery-cases/{case_id}/timeline",
        # Read-only scoring of a hypothetical scenario. Deliberately NOT a demo
        # route: it writes nothing and is a legitimate read of the decision
        # engine, so gating it behind DEMO_MODE would imply otherwise.
        "/api/v1/simulator/score",
        "/api/v1/webhooks/razorpay",
    ]
    # Demo routes are registered only under DEMO_MODE.
    if get_settings().demo_mode:
        expected += [
            "/api/v1/demo/evaluation",
            "/api/v1/demo/evaluation/recompute",
            "/api/v1/demo/reset",
            "/api/v1/demo/run-batch",
        ]
    assert api_v1_paths == sorted(expected)
