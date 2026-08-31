"""PostgreSQL integration tests for demo seeding."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from app.demo.constants import DEMO_ORGANIZATION_ID
from app.demo.factory import build_demo_seed_spec
from app.demo.seed import delete_demo_tenant, seed_demo_database
from app.demo.summary import summary_from_database
from app.domain.enums import RecoveryCaseStatus
from app.models.customer import Customer
from app.models.organization import Organization
from app.models.recovery_action import RecoveryAction
from app.models.recovery_case import RecoveryCase
from app.models.recovery_outcome import RecoveryOutcome
from app.models.transaction import Transaction
from tests.demo.conftest import postgres_available

pytestmark = pytest.mark.skipif(
    not postgres_available(),
    reason="PostgreSQL not available (set REVLOOP_TEST_DATABASE_URL)",
)


def test_seed_writes_to_migrated_postgresql(demo_settings, postgres_session) -> None:
    assert postgres_session is not None
    result = seed_demo_database(reset=True, settings=demo_settings)
    assert result.created is True

    summary = summary_from_database(postgres_session)
    assert summary.customers >= 50
    assert summary.transactions >= 500
    assert 80 <= summary.recovery_cases <= 120


def test_seed_without_reset_is_idempotent(demo_settings) -> None:
    first = seed_demo_database(reset=True, settings=demo_settings)
    second = seed_demo_database(reset=False, settings=demo_settings)
    assert first.created is True
    assert second.already_exists is True


def test_reset_reseed_is_deterministic(demo_settings, postgres_session) -> None:
    assert postgres_session is not None
    seed_demo_database(reset=True, settings=demo_settings)
    first = summary_from_database(postgres_session)

    seed_demo_database(reset=True, settings=demo_settings)
    second = summary_from_database(postgres_session)

    assert first.organization_id == second.organization_id
    assert first.customers == second.customers
    assert first.transactions == second.transactions
    assert first.recovery_cases == second.recovery_cases
    assert first.open_revenue_at_risk_minor == second.open_revenue_at_risk_minor
    assert first.historical_recovered_revenue_minor == second.historical_recovered_revenue_minor
    assert first.named_case_ids == second.named_case_ids


def test_reset_does_not_delete_unrelated_tenant_data(demo_settings, postgres_session) -> None:
    assert postgres_session is not None
    other_org_id = uuid.uuid5(uuid.NAMESPACE_DNS, "revloop-unrelated-org")
    other_customer_id = uuid.uuid5(uuid.NAMESPACE_DNS, "revloop-unrelated-customer")
    postgres_session.add(
        Organization(
            id=other_org_id,
            name="Unrelated Org",
            currency="INR",
            automation_enabled=False,
        )
    )
    postgres_session.add(
        Customer(
            id=other_customer_id,
            organization_id=other_org_id,
            external_id="unrelated-customer-001",
            display_name="Unrelated Customer",
            email="unrelated@example.com",
            segment="REGULAR",
            lifetime_value_minor=10000,
            is_synthetic=True,
        )
    )
    postgres_session.commit()

    seed_demo_database(reset=True, settings=demo_settings)

    assert (
        postgres_session.execute(
            select(Organization.id).where(Organization.id == other_org_id)
        ).scalar_one_or_none()
        == other_org_id
    )
    assert (
        postgres_session.execute(
            select(Customer.id).where(Customer.id == other_customer_id)
        ).scalar_one_or_none()
        == other_customer_id
    )

    delete_demo_tenant(postgres_session)
    postgres_session.execute(
        Customer.__table__.delete().where(Customer.id == other_customer_id)
    )
    postgres_session.execute(
        Organization.__table__.delete().where(Organization.id == other_org_id)
    )
    postgres_session.commit()


def test_seeded_records_satisfy_domain_checks(demo_settings, postgres_session) -> None:
    assert postgres_session is not None
    seed_demo_database(reset=True, settings=demo_settings)

    cases = postgres_session.execute(
        select(RecoveryCase).where(RecoveryCase.organization_id == DEMO_ORGANIZATION_ID)
    ).scalars().all()
    outcomes = postgres_session.execute(
        select(RecoveryOutcome).where(RecoveryOutcome.organization_id == DEMO_ORGANIZATION_ID)
    ).scalars().all()
    outcome_by_case = {item.case_id: item for item in outcomes}

    for case in cases:
        assert case.organization_id == DEMO_ORGANIZATION_ID
        if case.case_type == "PAYMENT_FAILURE":
            assert case.transaction_id is not None
            assert case.subscription_id is None
        if case.case_type == "SUBSCRIPTION_FAILURE":
            assert case.subscription_id is not None

        if case.status in {
            RecoveryCaseStatus.RECOVERED.value,
            RecoveryCaseStatus.FAILED.value,
            RecoveryCaseStatus.STOPPED.value,
        }:
            assert case.resolved_at is not None
            assert case.id in outcome_by_case
        else:
            assert case.resolved_at is None
            assert case.id not in outcome_by_case

    txn_count = postgres_session.execute(
        select(func.count())
        .select_from(Transaction)
        .where(Transaction.organization_id == DEMO_ORGANIZATION_ID)
    ).scalar_one()
    assert txn_count >= 500

    synthetic_customers = postgres_session.execute(
        select(func.count())
        .select_from(Customer)
        .where(
            Customer.organization_id == DEMO_ORGANIZATION_ID,
            Customer.is_synthetic.is_(True),
        )
    ).scalar_one()
    assert synthetic_customers >= 50

    idempotency_keys = postgres_session.execute(
        select(RecoveryAction.idempotency_key).where(
            RecoveryAction.organization_id == DEMO_ORGANIZATION_ID
        )
    ).scalars().all()
    assert len(idempotency_keys) == len(set(idempotency_keys))


def test_factory_spec_matches_seeded_counts(demo_settings, postgres_session) -> None:
    assert postgres_session is not None
    spec = build_demo_seed_spec()
    seed_demo_database(reset=True, settings=demo_settings)
    summary = summary_from_database(postgres_session)
    assert summary.customers == len(spec.customers)
    assert summary.transactions == len(spec.transactions)
    assert summary.recovery_cases == len(spec.recovery_cases)
