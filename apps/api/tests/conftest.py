import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.helpers.test_routes import register_test_routes


@pytest.fixture
def client_with_test_routes() -> TestClient:
    app = create_app()
    register_test_routes(app)
    return TestClient(app, raise_server_exceptions=False)
