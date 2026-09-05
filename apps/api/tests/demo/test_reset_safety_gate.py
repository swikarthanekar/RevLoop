"""Regression tests for the demo reset safety gate and its blast radius.

Two distinct failures are covered here, both of which reached the deployed
environment:

1. `POST /api/v1/demo/reset` answered `500 INTERNAL_ERROR` under
   `APP_ENV=production`, because the refusal was a plain `RuntimeError` that
   fell through to the catch-all handler. A refused reset is a deliberate
   safety decision and has to read like one.

2. `delete_demo_tenant` removed every `user_profiles` row in the demo
   organization, including hand-provisioned rows mapping real Supabase accounts
   onto the tenant. Running a reset would have locked the demo account out of
   the entire deployed app with `403 NO_ORGANIZATION_MEMBERSHIP`.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.errors import AppError
from app.demo.constants import (
    DEMO_AUTH_USER_ADMIN_ID,
    DEMO_AUTH_USER_ANALYST_ID,
    DEMO_AUTH_USER_OPERATOR_ID,
    DEMO_ORGANIZATION_ID,
)
from app.demo.seed import (
    SEED_MANAGED_AUTH_USER_IDS,
    ResetNotAllowedError,
    SeedError,
    assert_reset_allowed,
    capture_external_user_profiles,
    seed_demo_database,
)
from app.domain.enums import UserRole
from app.models.user_profile import UserProfile
from tests.demo.conftest import postgres_available, postgres_url

# --------------------------------------------------------------------------
# Gate semantics (no database required)
# --------------------------------------------------------------------------


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "app_env": "production",
        "demo_mode": True,
        "demo_reset_enabled": False,
    }
    base.update(overrides)
    return Settings.model_construct(**base)


def test_production_reset_refused_without_explicit_opt_in() -> None:
    with pytest.raises(ResetNotAllowedError) as excinfo:
        assert_reset_allowed(_settings())
    assert excinfo.value.code == "DEMO_RESET_NOT_ENABLED"


def test_production_reset_allowed_with_explicit_opt_in() -> None:
    """DEMO_MODE alone is not enough; DEMO_RESET_ENABLED unlocks it."""
    assert_reset_allowed(_settings(demo_reset_enabled=True)) is None


def test_demo_mode_disabled_refused_even_with_reset_opt_in() -> None:
    """The reset opt-in never re-enables a surface DEMO_MODE has switched off."""
    with pytest.raises(ResetNotAllowedError) as excinfo:
        assert_reset_allowed(_settings(demo_mode=False, demo_reset_enabled=True))
    assert excinfo.value.code == "DEMO_MODE_DISABLED"


def test_non_production_does_not_require_the_opt_in() -> None:
    assert_reset_allowed(_settings(app_env="development")) is None
    assert_reset_allowed(_settings(app_env="test")) is None


def test_refusal_is_a_typed_403_not_an_opaque_500() -> None:
    """The exact defect: a refusal that surfaced as INTERNAL_ERROR."""
    with pytest.raises(ResetNotAllowedError) as excinfo:
        assert_reset_allowed(_settings())
    error = excinfo.value
    assert isinstance(error, AppError)
    assert error.status_code == 403
    assert error.code != "INTERNAL_ERROR"
    # Still a SeedError, so callers treating seeding failures as one family
    # keep working.
    assert isinstance(error, SeedError)


def test_seed_manages_exactly_the_three_synthetic_auth_users() -> None:
    """Anything outside this set is externally provisioned and must survive."""
    assert SEED_MANAGED_AUTH_USER_IDS == frozenset(
        {DEMO_AUTH_USER_ADMIN_ID, DEMO_AUTH_USER_OPERATOR_ID, DEMO_AUTH_USER_ANALYST_ID}
    )


# --------------------------------------------------------------------------
# Blast radius (PostgreSQL required)
# --------------------------------------------------------------------------

pg_only = pytest.mark.skipif(
    not postgres_available(),
    reason="PostgreSQL not available (set REVLOOP_TEST_DATABASE_URL)",
)

#: Stands in for the hand-provisioned `demo@gmail.com` row in production.
EXTERNAL_AUTH_USER_ID = uuid.UUID("af7ff7a7-ab22-45dd-b0b5-11671c28b7c7")
EXTERNAL_PROFILE_ID = uuid.UUID("beeff00d-0000-4000-8000-000000000001")


@pytest.fixture()
def reset_settings(migrated_postgres: Engine | None) -> Settings:
    if migrated_postgres is None:
        pytest.skip("PostgreSQL not available")
    url = postgres_url()
    assert url is not None
    return Settings(app_env="test", demo_mode=True, database_url=url, _env_file=None)


@pytest.fixture()
def reset_session(migrated_postgres: Engine | None):
    """A session whose external sentinel profile is removed after each test.

    The row deliberately survives a reset, which is the whole point of these
    tests, so it also survives into the next one unless it is cleaned up here.
    """
    if migrated_postgres is None:
        pytest.skip("PostgreSQL not available")
    factory = sessionmaker(bind=migrated_postgres, future=True)
    with factory() as session:
        try:
            yield session
        finally:
            session.rollback()
            session.execute(
                UserProfile.__table__.delete().where(
                    UserProfile.auth_user_id == EXTERNAL_AUTH_USER_ID
                )
            )
            session.commit()


def _add_external_profile(session: Session) -> None:
    # Delete-then-insert, so a row left behind by an earlier interrupted run
    # cannot make the test fail for a reason unrelated to what it asserts.
    session.execute(
        UserProfile.__table__.delete().where(
            UserProfile.auth_user_id == EXTERNAL_AUTH_USER_ID
        )
    )
    session.add(
        UserProfile(
            id=EXTERNAL_PROFILE_ID,
            organization_id=DEMO_ORGANIZATION_ID,
            auth_user_id=EXTERNAL_AUTH_USER_ID,
            role=UserRole.ADMIN.value,
        )
    )
    session.commit()


def _external_profile(session: Session) -> UserProfile | None:
    session.expire_all()
    return session.execute(
        select(UserProfile).where(UserProfile.auth_user_id == EXTERNAL_AUTH_USER_ID)
    ).scalar_one_or_none()


@pg_only
def test_reset_preserves_externally_provisioned_profile(
    reset_settings: Settings,
    reset_session: Session,
) -> None:
    """The landmine: a reset must not lock out a hand-provisioned account."""
    seed_demo_database(reset=True, settings=reset_settings)
    _add_external_profile(reset_session)

    result = seed_demo_database(reset=True, settings=reset_settings)

    survivor = _external_profile(reset_session)
    assert survivor is not None, "reset deleted a hand-provisioned profile row"
    assert survivor.organization_id == DEMO_ORGANIZATION_ID
    assert survivor.role == UserRole.ADMIN.value
    assert survivor.id == EXTERNAL_PROFILE_ID, "profile identity must be stable"
    assert result.preserved_user_profiles == 1


@pg_only
def test_reset_still_rebuilds_the_seed_owned_profiles(
    reset_settings: Settings,
    reset_session: Session,
) -> None:
    """Preservation is scoped: the three synthetic profiles are reseeded."""
    seed_demo_database(reset=True, settings=reset_settings)
    _add_external_profile(reset_session)
    seed_demo_database(reset=True, settings=reset_settings)

    reset_session.expire_all()
    auth_ids = set(
        reset_session.execute(
            select(UserProfile.auth_user_id).where(
                UserProfile.organization_id == DEMO_ORGANIZATION_ID
            )
        ).scalars()
    )
    assert SEED_MANAGED_AUTH_USER_IDS <= auth_ids
    assert EXTERNAL_AUTH_USER_ID in auth_ids


@pg_only
def test_capture_excludes_seed_owned_profiles(
    reset_settings: Settings,
    reset_session: Session,
) -> None:
    seed_demo_database(reset=True, settings=reset_settings)
    _add_external_profile(reset_session)

    captured = capture_external_user_profiles(reset_session)

    assert [item.auth_user_id for item in captured] == [EXTERNAL_AUTH_USER_ID]


@pg_only
def test_repeated_reset_is_idempotent_for_preserved_profiles(
    reset_settings: Settings,
    reset_session: Session,
) -> None:
    """Three resets in a row must not duplicate or drop the external row."""
    seed_demo_database(reset=True, settings=reset_settings)
    _add_external_profile(reset_session)

    for _ in range(3):
        seed_demo_database(reset=True, settings=reset_settings)

    reset_session.expire_all()
    rows = reset_session.execute(
        select(UserProfile).where(UserProfile.auth_user_id == EXTERNAL_AUTH_USER_ID)
    ).scalars().all()
    assert len(rows) == 1


# --------------------------------------------------------------------------
# HTTP surface: a refused reset must read as a refusal
# --------------------------------------------------------------------------


@pg_only
def test_refused_reset_answers_403_over_http(migrated_postgres: Engine | None) -> None:
    """End-to-end proof of the production defect this file exists for.

    Production answered `500 {"code": "INTERNAL_ERROR"}` to a reset it had
    deliberately refused, which reads as "the service is broken" rather than
    "this is switched off on purpose".
    """
    from collections.abc import Generator

    from fastapi.testclient import TestClient

    from app.core.config import get_settings
    from app.core.deps import get_db
    from app.main import create_app

    assert migrated_postgres is not None
    url = postgres_url()
    assert url is not None
    refusing_settings = Settings.model_construct(
        app_env="production",
        demo_mode=True,
        demo_reset_enabled=False,
        database_url=url,
        dev_auth_user_id=DEMO_AUTH_USER_ADMIN_ID,
        dev_auth_organization_id=DEMO_ORGANIZATION_ID,
    )

    app = create_app()

    def override_get_db() -> Generator[Session, None, None]:
        session = sessionmaker(bind=migrated_postgres, future=True)()
        try:
            yield session
        finally:
            session.close()

    # The ADMIN gate is not what is under test here; the refusal must happen
    # for a caller who has already cleared it.
    from app.api.routes.demo import require_demo_admin
    from app.core.auth import AuthContext

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: refusing_settings
    app.dependency_overrides[require_demo_admin] = lambda: AuthContext(
        user_id=DEMO_AUTH_USER_ADMIN_ID,
        organization_id=DEMO_ORGANIZATION_ID,
        role=UserRole.ADMIN,
    )
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post("/api/v1/demo/reset")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    body = response.json()["error"]
    assert body["code"] == "DEMO_RESET_NOT_ENABLED"
    assert body["code"] != "INTERNAL_ERROR"
    # The message must say what to do, not just that something went wrong.
    assert "DEMO_RESET_ENABLED" in body["message"]


@pg_only
def test_seeding_fails_closed_when_the_real_model_is_unavailable(
    reset_settings: Settings,
    reset_session: Session,
) -> None:
    """A seed must never quietly produce heuristic numbers under a model label.

    Seeded recommendations are displayed under an "AI recovery decision"
    heading and stamped with a `model_version`. If inference failed and the
    seed fell back to the heuristic table, those rows would be labelled with
    whatever version the fallback reported and nobody would notice. The seed
    therefore runs with `allow_model_fallback=False` and raises instead.
    """
    from unittest.mock import patch

    from sqlalchemy import func

    from app.demo.analysis_seed import SeedAnalysisError
    from app.ml.service import ModelArtifactError
    from app.models.recovery_case import RecoveryCase

    seed_demo_database(reset=True, settings=reset_settings)

    def case_count() -> int:
        reset_session.expire_all()
        return int(
            reset_session.execute(
                select(func.count())
                .select_from(RecoveryCase)
                .where(RecoveryCase.organization_id == DEMO_ORGANIZATION_ID)
            ).scalar_one()
        )

    before = case_count()
    assert before > 0

    with patch(
        "app.ml.service.RecoveryPropensityModelService.score_actions",
        side_effect=ModelArtifactError("simulated missing artifact"),
    ):
        with pytest.raises(SeedAnalysisError):
            seed_demo_database(reset=True, settings=reset_settings)

    # The whole reset is one transaction, so a mid-way failure must leave the
    # previous tenant intact rather than publishing a half-deleted database.
    assert case_count() == before
