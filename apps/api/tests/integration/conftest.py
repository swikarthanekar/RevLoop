"""Fixtures for the Prompt 24 P0 integration suite.

One FastAPI app instance carries the whole flow so that a single client can post
the failure webhook, analyze, act, and post the success webhook exactly as a real
caller would. The only seams are the database session, the settings object, and
the Razorpay client injected into the action service.

Two deliberate configuration choices:

- Razorpay API credentials are left at their `dev-` defaults, so
  `acquire_razorpay_read_client` declines to build a client and the analysis
  downtime lookup performs no outbound HTTP. Payment-link execution still runs
  through the production adapter, using an injected mock transport.
- `gemini_api_key` is left unset, so the LLM path is disabled. The deterministic
  recovery engine must carry the entire flow on its own.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Generator
from urllib.parse import parse_qs, unquote

import httpx
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session, sessionmaker

from app.actions.service import RecoveryActionService
from app.api.routes.recovery_actions import get_recovery_action_service
from app.core.config import Settings, get_settings
from app.core.deps import get_db
from app.demo.constants import DEMO_AUTH_USER_ANALYST_ID, DEMO_ORGANIZATION_ID
from app.demo.seed import seed_demo_database
from app.main import create_app
from tests.demo.conftest import postgres_available, postgres_url
from tests.integrations.razorpay.razorpay_client_helpers import make_mock_client
from tests.workflows.helpers import create_customer

pytestmark = pytest.mark.skipif(
    not postgres_available(),
    reason="PostgreSQL not available (set REVLOOP_TEST_DATABASE_URL)",
)

WEBHOOK_SECRET = "dev-razorpay-webhook-secret"

ANALYST_HEADERS = {"Authorization": "Bearer dev-analyst"}
OPERATOR_HEADERS = {"Authorization": "Bearer dev-operator"}
ADMIN_HEADERS = {"Authorization": "Bearer dev-admin"}


def payment_link_payload(*, reference_id: str, amount: int, currency: str) -> dict:
    return {
        "id": f"plink_{reference_id[-12:]}",
        "entity": "payment_link",
        "reference_id": reference_id,
        "amount": amount,
        "currency": currency,
        "status": "created",
        "short_url": "https://rzp.io/i/mock-link",
    }


class PaymentLinkSpy:
    """Mock Razorpay payment-link transport that records every call.

    Used through the production `RazorpayClient`, so the adapter, signing and
    response mapping are all real; only the socket is replaced.
    """

    def __init__(self) -> None:
        self.post_count = 0
        self.get_count = 0
        self.last_reference: str | None = None
        self._links: dict[str, dict] = {}
        self._lock = threading.Lock()

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method.upper() == "GET" and "payment_links" in path:
            with self._lock:
                self.get_count += 1
            query = request.url.query
            if isinstance(query, bytes):
                query = query.decode()
            references = parse_qs(query).get("reference_id", [])
            if not references:
                return httpx.Response(200, json={"entity": "collection", "count": 0, "items": []})
            link = self._links.get(unquote(references[0]))
            if link is None:
                return httpx.Response(200, json={"entity": "collection", "count": 0, "items": []})
            return httpx.Response(200, json={"entity": "collection", "count": 1, "items": [link]})

        if request.method.upper() != "POST" or not path.endswith("/payment_links"):
            return httpx.Response(404)

        with self._lock:
            self.post_count += 1
        body = json.loads(request.content)
        reference = str(body["reference_id"])
        self.last_reference = reference
        payload = payment_link_payload(
            reference_id=reference,
            amount=int(body["amount"]),
            currency=str(body["currency"]),
        )
        self._links[reference] = payload
        return httpx.Response(200, json=payload)


@pytest.fixture(scope="session")
def integration_settings(migrated_postgres) -> Settings:
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
        razorpay_webhook_secret=SecretStr(WEBHOOK_SECRET),
        # `dev-` credentials mean no read client, so analysis performs no
        # outbound HTTP. Gemini stays unset, disabling the LLM path.
        gemini_api_key=None,
    )


@pytest.fixture(scope="session")
def integration_database(migrated_postgres, integration_settings):
    if migrated_postgres is None:
        pytest.skip("PostgreSQL not available")
    seed_demo_database(reset=True, settings=integration_settings)
    return migrated_postgres


@pytest.fixture
def session_factory(integration_database) -> Callable[[], Session]:
    return sessionmaker(bind=integration_database, autoflush=False, autocommit=False)


@pytest.fixture
def db_session(session_factory) -> Generator[Session, None, None]:
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def provider_spy() -> PaymentLinkSpy:
    return PaymentLinkSpy()


@pytest.fixture
def customer_external_id(session_factory) -> str:
    """A fresh customer per test, seeded before the business flow starts.

    Seeding a prerequisite customer is setup, not business mutation: everything
    from the failure event onward is produced by real application paths.
    """
    session = session_factory()
    try:
        customer = create_customer(session, organization_id=DEMO_ORGANIZATION_ID)
        external_id = customer.external_id
        session.commit()
    finally:
        session.close()
    return external_id


@pytest.fixture
def client(
    integration_database,
    integration_settings,
    session_factory,
    provider_spy: PaymentLinkSpy,
) -> Generator[TestClient, None, None]:
    """A single app carrying webhook, analysis, action, timeline and dashboard."""
    razorpay = make_mock_client(provider_spy.handler)
    app = create_app()

    def override_get_db() -> Generator[Session, None, None]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def override_get_settings() -> Settings:
        return integration_settings

    def override_action_service(db: Session = Depends(get_db)) -> RecoveryActionService:
        return RecoveryActionService(
            db,
            settings=integration_settings,
            razorpay_client=razorpay,
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = override_get_settings
    app.dependency_overrides[get_recovery_action_service] = override_action_service
    test_client = TestClient(app, raise_server_exceptions=False)
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()
