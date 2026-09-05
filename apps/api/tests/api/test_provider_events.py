"""Read-only provider-events view.

The value of this endpoint is that it makes webhook correctness visible without
being able to disturb it. Both halves are asserted: that it reports signature
and deduplication outcomes faithfully, and that it is genuinely read-only and
tenant-scoped.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.domain.enums import WebhookProcessingStatus
from app.models.organization import Organization
from app.models.webhook_event import WebhookEvent
from tests.demo.conftest import postgres_available, postgres_url

pytestmark = pytest.mark.skipif(
    not postgres_available(),
    reason="PostgreSQL not available (set REVLOOP_TEST_DATABASE_URL)",
)

ORG_ID = uuid.UUID("aa11bb22-cc33-4d44-8e55-ff6677889900")
OTHER_ORG_ID = uuid.UUID("bb11cc22-dd33-4e44-8f55-aa6677889900")
ADMIN_HEADERS = {"Authorization": "Bearer dev-admin"}
PATH = "/api/v1/provider-events"


@pytest.fixture()
def events_env(migrated_postgres: Engine | None):
    if migrated_postgres is None:
        pytest.skip("PostgreSQL not available")

    from collections.abc import Generator

    from fastapi.testclient import TestClient

    from app.core.config import Settings, get_settings
    from app.core.deps import get_db
    from app.main import create_app

    url = postgres_url()
    assert url is not None
    settings = Settings(
        app_env="test",
        demo_mode=True,
        database_url=url,
        dev_auth_user_id=uuid.uuid4(),
        dev_auth_organization_id=ORG_ID,
        _env_file=None,
    )

    factory = sessionmaker(bind=migrated_postgres, future=True)
    with factory() as setup:
        for org_id, name in ((ORG_ID, "Events Org"), (OTHER_ORG_ID, "Other Org")):
            if setup.get(Organization, org_id) is None:
                setup.add(Organization(id=org_id, name=name, currency="INR"))
        setup.execute(
            WebhookEvent.__table__.delete().where(
                WebhookEvent.organization_id.in_([ORG_ID, OTHER_ORG_ID])
            )
        )
        setup.commit()

    app = create_app()

    def override_get_db() -> Generator[Session, None, None]:
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: settings

    try:
        yield TestClient(app, raise_server_exceptions=False), factory
    finally:
        app.dependency_overrides.clear()
        with factory() as teardown:
            teardown.execute(
                WebhookEvent.__table__.delete().where(
                    WebhookEvent.organization_id.in_([ORG_ID, OTHER_ORG_ID])
                )
            )
            teardown.commit()


def _event(
    session: Session,
    *,
    organization_id: uuid.UUID = ORG_ID,
    event_id: str,
    event_type: str = "payment.failed",
    signature_valid: bool = True,
    status: str = WebhookProcessingStatus.PROCESSED.value,
    error: str | None = None,
    minutes_ago: int = 0,
    payload: dict | None = None,
) -> None:
    session.add(
        WebhookEvent(
            organization_id=organization_id,
            provider="razorpay",
            provider_event_id=event_id,
            event_type=event_type,
            signature_valid=signature_valid,
            processing_status=status,
            processing_error=error,
            payload=payload or {},
            received_at=datetime.now(tz=timezone.utc) - timedelta(minutes=minutes_ago),
        )
    )
    session.commit()


def test_reports_signature_and_processing_outcomes(events_env) -> None:
    client, factory = events_env
    with factory() as session:
        _event(session, event_id="evt_ok", minutes_ago=3)
        _event(
            session,
            event_id="evt_bad",
            signature_valid=False,
            status=WebhookProcessingStatus.FAILED.value,
            error="INVALID_WEBHOOK_SIGNATURE",
            minutes_ago=2,
        )
        _event(
            session,
            event_id="evt_dupe",
            status=WebhookProcessingStatus.IGNORED.value,
            error="Duplicate event id",
            minutes_ago=1,
        )

    body = client.get(PATH, headers=ADMIN_HEADERS).json()

    assert body["stats"]["total"] == 3
    assert body["stats"]["signature_valid"] == 2
    assert body["stats"]["signature_rejected"] == 1
    assert body["stats"]["processed"] == 1
    assert body["stats"]["failed"] == 1
    # A suppressed duplicate is recorded as IGNORED by the ingestion path.
    assert body["stats"]["duplicates_suppressed"] == 1

    by_id = {event["provider_event_id"]: event for event in body["events"]}
    assert by_id["evt_bad"]["signature_valid"] is False
    assert by_id["evt_bad"]["processing_error"] == "INVALID_WEBHOOK_SIGNATURE"
    assert by_id["evt_dupe"]["processing_status"] == "IGNORED"


def test_events_are_returned_newest_first(events_env) -> None:
    client, factory = events_env
    with factory() as session:
        _event(session, event_id="evt_old", minutes_ago=30)
        _event(session, event_id="evt_new", minutes_ago=1)

    events = client.get(PATH, headers=ADMIN_HEADERS).json()["events"]
    assert [event["provider_event_id"] for event in events] == ["evt_new", "evt_old"]


def test_is_scoped_to_the_callers_organization(events_env) -> None:
    """Another tenant's provider traffic must never appear here."""
    client, factory = events_env
    with factory() as session:
        _event(session, event_id="evt_mine")
        _event(session, organization_id=OTHER_ORG_ID, event_id="evt_theirs")

    body = client.get(PATH, headers=ADMIN_HEADERS).json()
    ids = {event["provider_event_id"] for event in body["events"]}
    assert ids == {"evt_mine"}
    assert body["stats"]["total"] == 1


def test_requires_authentication(events_env) -> None:
    client, _ = events_env
    assert client.get(PATH).status_code == 401


def test_reading_events_writes_nothing(events_env) -> None:
    """The property that makes this safe to open during a live demo."""
    client, factory = events_env
    with factory() as session:
        _event(session, event_id="evt_stable")

    def count() -> int:
        with factory() as session:
            return int(
                session.execute(
                    select(func.count()).select_from(WebhookEvent)
                ).scalar_one()
            )

    before = count()
    for _ in range(3):
        assert client.get(PATH, headers=ADMIN_HEADERS).status_code == 200
    assert count() == before


def test_there_is_no_replay_endpoint(events_env) -> None:
    """Deliberate absence, asserted so it is not added without thought.

    Replaying a webhook is a write path. Firing one during judging can corrupt
    the tenant while someone is watching, and the recorded history already
    tells the story without it.
    """
    client, _ = events_env
    paths = client.app.openapi()["paths"]
    replay_like = [
        path
        for path in paths
        if "provider-events" in path and path.rstrip("/") != PATH
    ]
    assert replay_like == []
    assert set(paths[PATH]) == {"get"}


def test_surfaces_the_case_a_payment_link_event_belongs_to(events_env) -> None:
    """Payment Links RevLoop created carry the case id in provider notes."""
    client, factory = events_env
    case_id = str(uuid.uuid4())
    with factory() as session:
        _event(
            session,
            event_id="evt_link_paid",
            event_type="payment_link.paid",
            payload={
                "payload": {
                    "payment_link": {
                        "entity": {"notes": {"revloop_case": case_id}}
                    }
                }
            },
        )

    events = client.get(PATH, headers=ADMIN_HEADERS).json()["events"]
    assert events[0]["case_id"] == case_id
