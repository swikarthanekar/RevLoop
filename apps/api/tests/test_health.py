from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app

client = TestClient(app)


def test_application_import_smoke() -> None:
    from app.main import app as imported_app

    assert imported_app.title == "RevLoop API"


def test_health_returns_contract_shape() -> None:
    settings = get_settings()
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "status": "ok",
        "database": "not_checked",
        "model": "loaded" if settings.model_bundle_path.exists() else "not_loaded",
        "version": settings.api_version,
    }


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
    assert api_v1_paths == [
        "/api/v1/",
        "/api/v1/dashboard/summary",
        "/api/v1/recovery-actions/{action_id}/approve",
        "/api/v1/recovery-actions/{action_id}/reject",
        "/api/v1/recovery-cases",
        "/api/v1/recovery-cases/{case_id}",
        "/api/v1/recovery-cases/{case_id}/actions",
        "/api/v1/recovery-cases/{case_id}/analyze",
        "/api/v1/recovery-cases/{case_id}/timeline",
        "/api/v1/webhooks/razorpay",
    ]
