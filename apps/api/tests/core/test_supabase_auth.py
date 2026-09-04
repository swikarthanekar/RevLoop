"""Supabase JWT verification tests (SupabaseAuthBackend)."""

from __future__ import annotations

import time
import uuid
from collections.abc import Generator

import jwt
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session, sessionmaker

from app.core.auth import SUPABASE_USER_AUDIENCE
from app.core.config import Settings, get_settings
from app.core.deps import get_db
from app.domain.enums import UserRole
from app.main import create_app
from app.models.user_profile import UserProfile
from tests.demo.conftest import postgres_available, postgres_url
from tests.helpers.test_routes import register_test_routes
from tests.workflows.helpers import create_organization

pytestmark = pytest.mark.skipif(
    not postgres_available(),
    reason="PostgreSQL not available (set REVLOOP_TEST_DATABASE_URL)",
)

JWT_SECRET = "test-supabase-jwt-secret-not-a-default-value"


@pytest.fixture(scope="session")
def supabase_auth_settings(migrated_postgres) -> Settings:
    if migrated_postgres is None:
        pytest.skip("PostgreSQL not available")
    url = postgres_url()
    if url is None:
        pytest.skip("PostgreSQL not available")
    return Settings(
        _env_file=None,
        app_env="production",
        database_url=url,
        supabase_jwt_secret=SecretStr(JWT_SECRET),
        razorpay_key_id=SecretStr("rzp_test_realkey"),
        razorpay_key_secret=SecretStr("real_secret_value"),
        razorpay_webhook_secret=SecretStr("real_webhook_secret"),
        public_app_base_url="https://revloop-demo.example.com",
    )


@pytest.fixture
def session_factory(migrated_postgres):
    return sessionmaker(bind=migrated_postgres, autoflush=False, autocommit=False)


@pytest.fixture
def db_session(session_factory) -> Generator[Session, None, None]:
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def auth_client(
    session_factory, supabase_auth_settings
) -> Generator[TestClient, None, None]:
    app = create_app()
    register_test_routes(app)

    def override_get_db() -> Generator[Session, None, None]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: supabase_auth_settings
    client = TestClient(app, raise_server_exceptions=False)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


def _make_token(
    *,
    sub: str,
    secret: str = JWT_SECRET,
    audience: str | None = SUPABASE_USER_AUDIENCE,
    expires_in: int = 3600,
) -> str:
    now = int(time.time())
    payload: dict[str, object] = {
        "sub": sub,
        "iat": now,
        "exp": now + expires_in,
        "role": "authenticated",
    }
    if audience is not None:
        payload["aud"] = audience
    return jwt.encode(payload, secret, algorithm="HS256")


def _add_profile(session: Session, *, role: UserRole) -> tuple[uuid.UUID, uuid.UUID]:
    org = create_organization(session)
    auth_user_id = uuid.uuid4()
    session.add(
        UserProfile(organization_id=org.id, auth_user_id=auth_user_id, role=role.value)
    )
    session.commit()
    return auth_user_id, org.id


def test_valid_token_resolves_organization_and_role_from_user_profiles(
    auth_client, db_session
) -> None:
    auth_user_id, org_id = _add_profile(db_session, role=UserRole.ADMIN)

    token = _make_token(sub=str(auth_user_id))
    response = auth_client.get("/_test/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == str(auth_user_id)
    assert body["organization_id"] == str(org_id)
    assert body["role"] == UserRole.ADMIN.value


def test_expired_token_is_rejected(auth_client, db_session) -> None:
    auth_user_id, _ = _add_profile(db_session, role=UserRole.ANALYST)

    token = _make_token(sub=str(auth_user_id), expires_in=-60)
    response = auth_client.get("/_test/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "TOKEN_EXPIRED"


def test_wrong_signing_secret_is_rejected(auth_client, db_session) -> None:
    auth_user_id, _ = _add_profile(db_session, role=UserRole.ANALYST)

    token = _make_token(
        sub=str(auth_user_id), secret="a-completely-different-secret-value-not-shared"
    )
    response = auth_client.get("/_test/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_wrong_audience_is_rejected(auth_client, db_session) -> None:
    """Rejects a token signed with the same project secret but issued for a
    different purpose (e.g. the anon/service-role key), not only a token
    signed with a different secret entirely."""
    auth_user_id, _ = _add_profile(db_session, role=UserRole.ANALYST)

    token = _make_token(sub=str(auth_user_id), audience="anon")
    response = auth_client.get("/_test/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_malformed_subject_claim_is_rejected(auth_client) -> None:
    token = jwt.encode(
        {
            "sub": "not-a-uuid",
            "aud": SUPABASE_USER_AUDIENCE,
            "exp": int(time.time()) + 3600,
        },
        JWT_SECRET,
        algorithm="HS256",
    )
    response = auth_client.get("/_test/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_verified_token_without_user_profile_is_forbidden(auth_client) -> None:
    """A real Supabase account that was never provisioned into an
    organization must be a distinct, clear failure -- not a generic 401 that
    looks like a credential problem, and not silently granted access."""
    token = _make_token(sub=str(uuid.uuid4()))
    response = auth_client.get("/_test/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NO_ORGANIZATION_MEMBERSHIP"


def test_missing_token_is_unauthorized(auth_client) -> None:
    response = auth_client.get("/_test/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
