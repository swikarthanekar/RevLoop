"""Shared fixtures for read API integration tests."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.auth import AuthContext, get_current_user
from app.core.config import Settings, get_settings
from app.core.deps import get_db
from app.demo.constants import (
    DEMO_AUTH_USER_ANALYST_ID,
    DEMO_ORGANIZATION_ID,
)
from app.demo.seed import seed_demo_database
from app.domain.enums import RecoveryCaseStatus, UserRole
from app.main import create_app
from app.models.recovery_case import RecoveryCase
from tests.demo.conftest import postgres_available, postgres_url
from tests.workflows.helpers import create_case, create_customer

pytestmark = pytest.mark.skipif(
    not postgres_available(),
    reason="PostgreSQL not available (set REVLOOP_TEST_DATABASE_URL)",
)

DEMO_AUTH_HEADERS = {"Authorization": "Bearer dev-analyst"}


@pytest.fixture(scope="session")
def api_demo_settings(migrated_postgres) -> Settings:
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
    )


@pytest.fixture(scope="session")
def seeded_database(migrated_postgres, api_demo_settings):
    if migrated_postgres is None:
        pytest.skip("PostgreSQL not available")
    seed_demo_database(reset=True, settings=api_demo_settings)
    return migrated_postgres


@pytest.fixture
def db_session(seeded_database) -> Generator[Session, None, None]:
    session = sessionmaker(bind=seeded_database, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def api_client(seeded_database, api_demo_settings) -> Generator[TestClient, None, None]:
    app = create_app()

    def override_get_db() -> Generator[Session, None, None]:
        session = sessionmaker(bind=seeded_database, autoflush=False, autocommit=False)()
        try:
            yield session
        finally:
            session.close()

    def override_get_settings() -> Settings:
        return api_demo_settings

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = override_get_settings
    client = TestClient(app, raise_server_exceptions=False)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def other_org_client(seeded_database) -> Generator[TestClient, None, None]:
    import uuid

    other_org_id = uuid.uuid5(uuid.NAMESPACE_DNS, "revloop-api-other-org")
    other_user_id = uuid.uuid5(uuid.NAMESPACE_DNS, "revloop-api-other-user")

    app = create_app()

    def override_get_db() -> Generator[Session, None, None]:
        session = sessionmaker(bind=seeded_database, autoflush=False, autocommit=False)()
        try:
            yield session
        finally:
            session.close()

    async def override_get_current_user() -> AuthContext:
        return AuthContext(
            user_id=other_user_id,
            organization_id=other_org_id,
            role=UserRole.ANALYST,
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    client = TestClient(app, raise_server_exceptions=False)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def empty_org_client(seeded_database) -> Generator[TestClient, None, None]:
    import uuid

    empty_org_id = uuid.uuid5(uuid.NAMESPACE_DNS, "revloop-api-empty-org")
    empty_user_id = uuid.uuid5(uuid.NAMESPACE_DNS, "revloop-api-empty-user")

    app = create_app()

    def override_get_db() -> Generator[Session, None, None]:
        session = sessionmaker(bind=seeded_database, autoflush=False, autocommit=False)()
        try:
            yield session
        finally:
            session.close()

    async def override_get_current_user() -> AuthContext:
        return AuthContext(
            user_id=empty_user_id,
            organization_id=empty_org_id,
            role=UserRole.ANALYST,
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    client = TestClient(app, raise_server_exceptions=False)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def demo_org_id() -> str:
    return str(DEMO_ORGANIZATION_ID)


@pytest.fixture
def analyzable_case(db_session: Session) -> Generator[RecoveryCase, None, None]:
    customer = create_customer(db_session, organization_id=DEMO_ORGANIZATION_ID)
    case = create_case(
        db_session,
        organization_id=DEMO_ORGANIZATION_ID,
        customer_id=customer.id,
        status=RecoveryCaseStatus.DETECTED,
    )
    db_session.commit()
    yield case


@pytest.fixture
def session_factory(seeded_database):
    return sessionmaker(bind=seeded_database, autoflush=False, autocommit=False)


@pytest.fixture
def fresh_db_session(session_factory) -> Generator[Session, None, None]:
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
