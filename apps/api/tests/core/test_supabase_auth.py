"""Supabase JWT verification tests (SupabaseAuthBackend)."""

from __future__ import annotations

import time
import uuid
from collections.abc import Generator

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePrivateKey
from fastapi.testclient import TestClient
from jwt.algorithms import ECAlgorithm
from pydantic import SecretStr
from sqlalchemy.orm import Session, sessionmaker

import app.core.auth as auth_module
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
SUPABASE_URL = "https://project.supabase.co"
JWKS_URL = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
ES256_KID = "test-es256-kid-1"


@pytest.fixture(autouse=True)
def clear_jwks_client_cache() -> Generator[None, None, None]:
    """SupabaseAuthBackend caches PyJWKClient instances (and each instance
    caches its own fetched JWK Set) at module level, keyed by URL, so the
    cache actually survives across the per-request backend instances this
    codebase constructs. Every test in this file reuses JWKS_URL, so without
    clearing this, a later test would silently see an earlier test's cached
    (and monkeypatched) client."""
    auth_module._jwks_clients.clear()
    yield
    auth_module._jwks_clients.clear()


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
        supabase_url=SUPABASE_URL,
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


def _generate_es256_keypair() -> EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


def _jwks_document(private_key: EllipticCurvePrivateKey, *, kid: str = ES256_KID) -> dict:
    jwk = ECAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    jwk["kid"] = kid
    jwk["alg"] = "ES256"
    jwk["use"] = "sig"
    return {"keys": [jwk]}


def _make_es256_token(
    *,
    sub: str,
    private_key: EllipticCurvePrivateKey,
    kid: str = ES256_KID,
    audience: str | None = SUPABASE_USER_AUDIENCE,
    expires_in: int = 3600,
) -> str:
    now = int(time.time())
    payload: dict[str, object] = {"sub": sub, "iat": now, "exp": now + expires_in}
    if audience is not None:
        payload["aud"] = audience
    return jwt.encode(payload, private_key, algorithm="ES256", headers={"kid": kid})


def _stub_jwks_fetch(monkeypatch: pytest.MonkeyPatch, jwks: dict) -> None:
    """Avoid a real network call to Supabase's JWKS endpoint: pre-populate
    the cached PyJWKClient's fetch with canned data. Requires the
    clear_jwks_client_cache fixture to have already reset the module cache
    for this test."""
    client = auth_module._get_jwks_client(JWKS_URL)
    monkeypatch.setattr(client, "fetch_data", lambda: jwks)


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


class TestAsymmetricSigningKeys:
    """Newer Supabase projects (and any project migrated to "JWT Signing
    Keys" in the dashboard) sign user access tokens asymmetrically -- ES256
    verified against the project's public JWKS document -- rather than with
    the legacy shared HS256 secret every other test in this file exercises.
    Which one a given token uses is read from its own `alg` header."""

    def test_valid_es256_token_resolves_organization_and_role(
        self, auth_client, db_session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        auth_user_id, org_id = _add_profile(db_session, role=UserRole.OPERATOR)
        private_key = _generate_es256_keypair()
        _stub_jwks_fetch(monkeypatch, _jwks_document(private_key))

        token = _make_es256_token(sub=str(auth_user_id), private_key=private_key)
        response = auth_client.get("/_test/me", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 200
        body = response.json()
        assert body["user_id"] == str(auth_user_id)
        assert body["organization_id"] == str(org_id)
        assert body["role"] == UserRole.OPERATOR.value

    def test_token_signed_by_an_unknown_key_is_rejected(
        self, auth_client, db_session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A token whose `kid` isn't in the project's current JWKS -- signed
        by an unrelated key, not a rotation/caching timing issue here since
        the JWKS is stubbed fresh per test."""
        auth_user_id, _ = _add_profile(db_session, role=UserRole.ANALYST)
        real_key = _generate_es256_keypair()
        attacker_key = _generate_es256_keypair()
        _stub_jwks_fetch(monkeypatch, _jwks_document(real_key))

        token = _make_es256_token(sub=str(auth_user_id), private_key=attacker_key)
        response = auth_client.get("/_test/me", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHORIZED"

    def test_expired_es256_token_is_rejected(
        self, auth_client, db_session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        auth_user_id, _ = _add_profile(db_session, role=UserRole.ANALYST)
        private_key = _generate_es256_keypair()
        _stub_jwks_fetch(monkeypatch, _jwks_document(private_key))

        token = _make_es256_token(sub=str(auth_user_id), private_key=private_key, expires_in=-60)
        response = auth_client.get("/_test/me", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "TOKEN_EXPIRED"

    def test_jwks_connection_failure_is_service_unavailable_not_unauthorized(
        self, auth_client, db_session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Being unable to reach Supabase's JWKS endpoint is our system's
        problem, transient and worth retrying -- distinct from the token
        itself being invalid, and must not be reported the same way."""
        auth_user_id, _ = _add_profile(db_session, role=UserRole.ANALYST)
        private_key = _generate_es256_keypair()
        client = auth_module._get_jwks_client(JWKS_URL)

        def _raise_connection_error() -> dict:
            raise jwt.PyJWKClientConnectionError("could not reach jwks endpoint")

        monkeypatch.setattr(client, "fetch_data", _raise_connection_error)

        token = _make_es256_token(sub=str(auth_user_id), private_key=private_key)
        response = auth_client.get("/_test/me", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"

    def test_unconfigured_supabase_url_fails_closed_with_a_clear_message(
        self, session_factory, db_session
    ) -> None:
        """An ES256 token with no SUPABASE_URL configured to verify it
        against must fail with a diagnosable config error, not a bare 401
        that looks like a credential problem."""
        settings = Settings(
            _env_file=None,
            app_env="production",
            database_url=postgres_url(),
            supabase_jwt_secret=SecretStr(JWT_SECRET),
            supabase_url=None,
            razorpay_key_id=SecretStr("rzp_test_realkey"),
            razorpay_key_secret=SecretStr("real_secret_value"),
            razorpay_webhook_secret=SecretStr("real_webhook_secret"),
            public_app_base_url="https://revloop-demo.example.com",
        )
        app = create_app()
        register_test_routes(app)

        def override_get_db() -> Generator[Session, None, None]:
            session = session_factory()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_settings] = lambda: settings
        client = TestClient(app, raise_server_exceptions=False)

        auth_user_id, _ = _add_profile(db_session, role=UserRole.ANALYST)
        private_key = _generate_es256_keypair()
        token = _make_es256_token(sub=str(auth_user_id), private_key=private_key)

        response = client.get("/_test/me", headers={"Authorization": f"Bearer {token}"})
        app.dependency_overrides.clear()

        assert response.status_code == 500
        assert response.json()["error"]["code"] == "AUTH_NOT_CONFIGURED"

    def test_hs256_and_es256_tokens_are_both_accepted_in_the_same_deployment(
        self, auth_client, db_session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Which algorithm a token uses is read per-token from its own `alg`
        header, not assumed from a single fixed backend configuration."""
        private_key = _generate_es256_keypair()
        _stub_jwks_fetch(monkeypatch, _jwks_document(private_key))

        hs256_user, _ = _add_profile(db_session, role=UserRole.ADMIN)
        es256_user, _ = _add_profile(db_session, role=UserRole.OPERATOR)

        hs256_token = _make_token(sub=str(hs256_user))
        es256_token = _make_es256_token(sub=str(es256_user), private_key=private_key)

        hs256_response = auth_client.get(
            "/_test/me", headers={"Authorization": f"Bearer {hs256_token}"}
        )
        es256_response = auth_client.get(
            "/_test/me", headers={"Authorization": f"Bearer {es256_token}"}
        )

        assert hs256_response.status_code == 200
        assert hs256_response.json()["role"] == UserRole.ADMIN.value
        assert es256_response.status_code == 200
        assert es256_response.json()["role"] == UserRole.OPERATOR.value
