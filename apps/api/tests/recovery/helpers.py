"""Shared helpers for recovery analysis hardening tests."""

from __future__ import annotations

from collections.abc import Generator
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models.recovery_case import RecoveryCase

PRIORITY_SCORE_QUANTUM = Decimal("0.000001")


def quantize_priority_score(value: Decimal) -> Decimal:
    return value.quantize(PRIORITY_SCORE_QUANTUM, rounding=ROUND_HALF_UP)


@pytest.fixture
def session_factory(recovery_seeded_database):
    return sessionmaker(bind=recovery_seeded_database, autoflush=False, autocommit=False)


def load_case_fresh(
    session_factory,
    *,
    case_id: UUID,
    organization_id: UUID,
) -> RecoveryCase:
    session = session_factory()
    try:
        return session.execute(
            select(RecoveryCase).where(
                RecoveryCase.id == case_id,
                RecoveryCase.organization_id == organization_id,
            )
        ).scalar_one()
    finally:
        session.close()


@pytest.fixture
def fresh_db_session(session_factory) -> Generator[Session, None, None]:
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
