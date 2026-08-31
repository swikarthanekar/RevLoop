"""Shared fixtures for workflow state machine tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from tests.demo.conftest import postgres_available

pytestmark = pytest.mark.skipif(
    not postgres_available(),
    reason="PostgreSQL not available (set REVLOOP_TEST_DATABASE_URL)",
)


@pytest.fixture
def workflow_session(postgres_session: Session) -> Session:
    yield postgres_session
    postgres_session.rollback()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
