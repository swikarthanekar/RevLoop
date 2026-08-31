from fastapi.testclient import TestClient


def test_standard_error_envelope_shape(client_with_test_routes: TestClient) -> None:
    response = client_with_test_routes.get("/_test/not-found")

    assert response.status_code == 404
    payload = response.json()
    assert set(payload.keys()) == {"error"}
    assert set(payload["error"].keys()) == {"code", "message", "details", "request_id"}
    assert payload["error"]["code"] == "CASE_NOT_FOUND"
    assert isinstance(payload["error"]["message"], str)
    assert isinstance(payload["error"]["details"], dict)
    assert isinstance(payload["error"]["request_id"], str)


def test_internal_errors_do_not_expose_stack_traces(client_with_test_routes: TestClient) -> None:
    response = client_with_test_routes.get("/_test/internal-error")

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert "super-secret-token" not in response.text
    assert "Traceback" not in response.text
    assert "request_id" in body["error"]
