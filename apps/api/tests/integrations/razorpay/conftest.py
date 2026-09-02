"""Shared fixtures for Razorpay webhook integration tests."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.deps import get_db
from app.demo.constants import DEMO_AUTH_USER_ANALYST_ID, DEMO_ORGANIZATION_ID
from app.main import create_app
from tests.demo.conftest import postgres_available, postgres_url

pytestmark = pytest.mark.skipif(
    not postgres_available(),
    reason="PostgreSQL not available (set REVLOOP_TEST_DATABASE_URL)",
)

WEBHOOK_PATH = "/api/v1/webhooks/razorpay"


@pytest.fixture(scope="session")
def webhook_test_settings(migrated_postgres) -> Settings:
    if migrated_postgres is None:
        pytest.skip("PostgreSQL not available")
    url = postgres_url()
    if url is None:
        pytest.skip("PostgreSQL not available")
    return Settings(
        app_env="test",
        demo_mode=True,
        database_url=url,
        dev_auth_user_id=DEMO_AUTH_USER_ANALYST_ID,
        dev_auth_organization_id=DEMO_ORGANIZATION_ID,
        razorpay_webhook_secret="dev-razorpay-webhook-secret",
    )


@pytest.fixture(scope="session")
def webhook_seeded_database(migrated_postgres, webhook_test_settings):
    if migrated_postgres is None:
        pytest.skip("PostgreSQL not available")
    from app.demo.seed import seed_demo_database

    seed_demo_database(reset=True, settings=webhook_test_settings)
    return migrated_postgres


@pytest.fixture
def webhook_session_factory(webhook_seeded_database):
    return sessionmaker(bind=webhook_seeded_database, autoflush=False, autocommit=False)


@pytest.fixture
def webhook_db_session(webhook_session_factory) -> Generator[Session, None, None]:
    session = webhook_session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def webhook_client(
    webhook_seeded_database,
    webhook_test_settings,
) -> Generator[TestClient, None, None]:
    app = create_app()

    def override_get_db() -> Generator[Session, None, None]:
        session = sessionmaker(bind=webhook_seeded_database, autoflush=False, autocommit=False)()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: webhook_test_settings
    client = TestClient(app, raise_server_exceptions=False)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


def post_webhook(client: TestClient, raw_body: bytes, headers: dict[str, str]):
    return client.post(WEBHOOK_PATH, content=raw_body, headers=headers)
