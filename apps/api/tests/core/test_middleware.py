from fastapi.testclient import TestClient

from app.core.middleware import REQUEST_ID_HEADER, VALID_REQUEST_ID, generate_request_id
from app.main import app

client = TestClient(app)


def test_generate_request_id_format() -> None:
    request_id = generate_request_id()
    assert request_id.startswith("req_")
    assert VALID_REQUEST_ID.match(request_id)


def test_success_response_includes_generated_request_id() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    request_id = response.headers[REQUEST_ID_HEADER]
    assert request_id.startswith("req_")


def test_success_response_preserves_valid_incoming_request_id() -> None:
    incoming = "req_clientprovided123456"
    response = client.get("/health", headers={REQUEST_ID_HEADER: incoming})

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == incoming


def test_invalid_incoming_request_id_is_replaced() -> None:
    response = client.get("/health", headers={REQUEST_ID_HEADER: "bad id!"})

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER].startswith("req_")
    assert response.headers[REQUEST_ID_HEADER] != "bad id!"


def test_error_response_includes_request_id_header_and_body(
    client_with_test_routes: TestClient,
) -> None:
    incoming = "req_errorpath12345678"
    response = client_with_test_routes.get(
        "/_test/not-found",
        headers={REQUEST_ID_HEADER: incoming},
    )

    assert response.status_code == 404
    assert response.headers[REQUEST_ID_HEADER] == incoming

    body = response.json()
    assert body["error"]["code"] == "CASE_NOT_FOUND"
    assert body["error"]["message"] == "Recovery case was not found."
    assert body["error"]["details"] == {}
    assert body["error"]["request_id"] == incoming
