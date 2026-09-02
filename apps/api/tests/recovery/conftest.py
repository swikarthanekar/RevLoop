"""Shared fixtures for recovery analysis tests."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.demo.constants import (
    DEMO_AUTH_USER_ANALYST_ID,
    DEMO_ORGANIZATION_ID,
)
from app.demo.seed import seed_demo_database
from app.domain.enums import RecoveryCaseStatus
from app.ml.service import clear_model_bundle_cache
from app.models.merchant_policy import MerchantPolicy
from app.models.recovery_case import RecoveryCase
from tests.demo.conftest import postgres_available, postgres_url
from tests.workflows.helpers import create_case, create_customer

pytestmark = pytest.mark.skipif(
    not postgres_available(),
    reason="PostgreSQL not available (set REVLOOP_TEST_DATABASE_URL)",
)

CANONICAL_ARTIFACT_PATH = (
    Path(__file__).resolve().parents[2] / "app" / "ml" / "artifacts" / "recovery_model.joblib"
)
CANONICAL_ARTIFACT_SHA256 = (
    "152ecbc8ab4e5bc5b583059a824ea562363f920e238b4b7aa283d9cb74447ef2"
)


@pytest.fixture(scope="session")
def recovery_demo_settings(migrated_postgres) -> Settings:
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
def recovery_seeded_database(migrated_postgres, recovery_demo_settings):
    if migrated_postgres is None:
        pytest.skip("PostgreSQL not available")
    seed_demo_database(reset=True, settings=recovery_demo_settings)
    return migrated_postgres


@pytest.fixture
def db_session(recovery_seeded_database) -> Generator[Session, None, None]:
    session = sessionmaker(bind=recovery_seeded_database, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()


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


@pytest.fixture(autouse=True)
def reset_model_cache() -> None:
    clear_model_bundle_cache()
    yield
    clear_model_bundle_cache()


def get_detected_case(session: Session, organization_id: UUID) -> RecoveryCase:
    case = session.execute(
        select(RecoveryCase).where(
            RecoveryCase.organization_id == organization_id,
            RecoveryCase.status == RecoveryCaseStatus.DETECTED.value,
        )
    ).scalars().first()
    if case is None:
        raise RuntimeError("Expected at least one DETECTED recovery case in seeded demo data.")
    return case


def require_merchant_policy(session: Session, organization_id: UUID) -> MerchantPolicy:
    policy = session.execute(
        select(MerchantPolicy).where(MerchantPolicy.organization_id == organization_id)
    ).scalar_one_or_none()
    if policy is None:
        raise RuntimeError("Expected merchant policy for demo organization.")
    return policy
