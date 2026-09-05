"""HTTP-level tests for the demo-only routes, against PostgreSQL.

Covers demo-mode route gating, ADMIN authorization, reset determinism and
isolation, batch determinism and provenance, and the mandatory provider
zero-call regression.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.deps import get_db
from app.demo.constants import (
    DEMO_AUTH_USER_ADMIN_ID,
    DEMO_ORGANIZATION_ID,
    RECOVERY_CASE_COUNT,
)
from app.demo.evaluation import DEMO_BATCH_CASE_COUNT
from app.demo.seed import seed_demo_database
from app.main import create_app
from app.models.merchant_policy import MerchantPolicy
from app.models.organization import Organization
from app.models.recovery_case import RecoveryCase
from tests.demo.conftest import postgres_available, postgres_url
from tests.workflows.helpers import create_case, create_customer

pytestmark = pytest.mark.skipif(
    not postgres_available(),
    reason="PostgreSQL not available (set REVLOOP_TEST_DATABASE_URL)",
)

ADMIN_HEADERS = {"Authorization": "Bearer dev-admin"}
OPERATOR_HEADERS = {"Authorization": "Bearer dev-operator"}
ANALYST_HEADERS = {"Authorization": "Bearer dev-analyst"}

RESET_PATH = "/api/v1/demo/reset"
BATCH_PATH = "/api/v1/demo/run-batch"

SENTINEL_ORG_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")
SENTINEL_CUSTOMER_ID = uuid.UUID("11111111-2222-3333-4444-666666666666")
SENTINEL_CASE_ID = uuid.UUID("11111111-2222-3333-4444-777777777777")


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture(scope="session")
def demo_route_settings(migrated_postgres: Engine | None) -> Settings:
    if migrated_postgres is None:
        pytest.skip("PostgreSQL not available")
    url = postgres_url()
    assert url is not None
    return Settings(
        app_env="test",
        demo_mode=True,
        database_url=url,
        dev_auth_user_id=DEMO_AUTH_USER_ADMIN_ID,
        dev_auth_organization_id=DEMO_ORGANIZATION_ID,
    )


@pytest.fixture
def demo_database(migrated_postgres: Engine | None, demo_route_settings: Settings) -> Engine:
    if migrated_postgres is None:
        pytest.skip("PostgreSQL not available")
    seed_demo_database(reset=True, settings=demo_route_settings)
    return migrated_postgres


def _build_client(engine: Engine, settings: Settings) -> TestClient:
    app = create_app()

    def override_get_db() -> Generator[Session, None, None]:
        session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def demo_client(
    demo_database: Engine, demo_route_settings: Settings
) -> Generator[TestClient, None, None]:
    client = _build_client(demo_database, demo_route_settings)
    try:
        yield client
    finally:
        client.app.dependency_overrides.clear()


@pytest.fixture
def demo_session(demo_database: Engine) -> Generator[Session, None, None]:
    session = sessionmaker(bind=demo_database, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()


class ProviderSpy:
    """Counts every call across the Razorpay provider boundary."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def record(self, name: str):
        def _spy(*_args: object, **_kwargs: object):
            self.calls.append(name)
            raise AssertionError(f"Provider adapter '{name}' must not be called.")

        return _spy


@pytest.fixture
def provider_spy(monkeypatch: pytest.MonkeyPatch) -> ProviderSpy:
    """Install spies on every public provider operation.

    Patched at the application/provider boundary — the adapter functions and the
    client transport methods — not merely at the HTTP socket.
    """
    spy = ProviderSpy()
    targets = (
        ("app.integrations.razorpay.provider.acquire_razorpay_read_client", "acquire_read_client"),
        ("app.integrations.razorpay.provider.create_razorpay_read_client", "create_read_client"),
        ("app.integrations.razorpay.client.RazorpayClient.get_json", "client.get_json"),
        ("app.integrations.razorpay.client.RazorpayClient.post_json", "client.post_json"),
        ("app.integrations.razorpay.payments.fetch_payment", "fetch_payment"),
        ("app.integrations.razorpay.payment_links.create_payment_link", "create_payment_link"),
        (
            "app.integrations.razorpay.payment_links.fetch_payment_links_by_reference",
            "fetch_payment_links_by_reference",
        ),
        ("app.integrations.razorpay.downtime.fetch_downtimes", "fetch_downtimes"),
        ("app.integrations.razorpay.downtime.fetch_downtime_by_id", "fetch_downtime_by_id"),
        ("app.integrations.razorpay.webhooks.verify_webhook_signature", "verify_webhook_signature"),
    )
    for target, name in targets:
        monkeypatch.setattr(target, spy.record(name), raising=True)
    return spy


def _registered_paths(client: TestClient) -> set[str]:
    """Externally observable route set."""
    return set(client.app.openapi()["paths"])


def _seed_sentinel(session: Session) -> None:
    """Insert a non-demo organization with its own case."""
    if session.get(Organization, SENTINEL_ORG_ID) is not None:
        return
    session.add(
        Organization(
            id=SENTINEL_ORG_ID,
            name="Sentinel Non-Demo Org",
            currency="INR",
        )
    )
    session.flush()
    create_customer(
        session,
        organization_id=SENTINEL_ORG_ID,
        customer_id=SENTINEL_CUSTOMER_ID,
    )
    create_case(
        session,
        organization_id=SENTINEL_ORG_ID,
        customer_id=SENTINEL_CUSTOMER_ID,
        case_id=SENTINEL_CASE_ID,
    )
    session.commit()


# --------------------------------------------------------------------------
# A. Demo-mode route gating
# --------------------------------------------------------------------------


def test_demo_routes_are_not_registered_when_demo_mode_is_false(
    migrated_postgres: Engine | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if migrated_postgres is None:
        pytest.skip("PostgreSQL not available")
    url = postgres_url()
    assert url is not None
    disabled = Settings(
        app_env="test",
        demo_mode=False,
        database_url=url,
        dev_auth_user_id=DEMO_AUTH_USER_ADMIN_ID,
        dev_auth_organization_id=DEMO_ORGANIZATION_ID,
    )
    monkeypatch.setattr("app.main.get_settings", lambda: disabled)
    client = _build_client(migrated_postgres, disabled)

    registered = _registered_paths(client)
    assert RESET_PATH not in registered
    assert BATCH_PATH not in registered

    # Even an ADMIN gets 404: the route does not exist.
    assert client.post(RESET_PATH, headers=ADMIN_HEADERS).status_code == 404
    assert client.post(BATCH_PATH, headers=ADMIN_HEADERS).status_code == 404


def test_demo_routes_are_registered_when_demo_mode_is_true(demo_client: TestClient) -> None:
    registered = _registered_paths(demo_client)
    assert RESET_PATH in registered
    assert BATCH_PATH in registered


def test_demo_mode_off_does_not_leak_into_a_later_app(
    demo_database: Engine,
    demo_route_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Router construction must not mutate shared module state."""
    url = postgres_url()
    assert url is not None
    disabled = Settings(app_env="test", demo_mode=False, database_url=url)
    monkeypatch.setattr("app.main.get_settings", lambda: disabled)
    disabled_client = _build_client(demo_database, disabled)
    assert disabled_client.post(BATCH_PATH, headers=ADMIN_HEADERS).status_code == 404

    monkeypatch.setattr("app.main.get_settings", lambda: demo_route_settings)
    enabled_client = _build_client(demo_database, demo_route_settings)
    assert enabled_client.post(BATCH_PATH, headers=ADMIN_HEADERS).status_code == 200


# --------------------------------------------------------------------------
# B. Authorization
# --------------------------------------------------------------------------


@pytest.mark.parametrize("path", [RESET_PATH, BATCH_PATH])
def test_unauthenticated_caller_is_rejected(demo_client: TestClient, path: str) -> None:
    response = demo_client.post(path)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.parametrize("path", [RESET_PATH, BATCH_PATH])
@pytest.mark.parametrize("headers", [ANALYST_HEADERS, OPERATOR_HEADERS])
def test_non_admin_caller_is_rejected(
    demo_client: TestClient, path: str, headers: dict[str, str]
) -> None:
    response = demo_client.post(path, headers=headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ROLE_NOT_ALLOWED"


@pytest.mark.parametrize("path", [RESET_PATH, BATCH_PATH])
def test_admin_caller_is_allowed(demo_client: TestClient, path: str) -> None:
    assert demo_client.post(path, headers=ADMIN_HEADERS).status_code == 200


def test_environment_and_role_gates_are_independent(
    migrated_postgres: Engine | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DEMO_MODE=false + ADMIN is still 404, not 403."""
    if migrated_postgres is None:
        pytest.skip("PostgreSQL not available")
    url = postgres_url()
    assert url is not None
    disabled = Settings(
        app_env="test",
        demo_mode=False,
        database_url=url,
        dev_auth_user_id=DEMO_AUTH_USER_ADMIN_ID,
        dev_auth_organization_id=DEMO_ORGANIZATION_ID,
    )
    monkeypatch.setattr("app.main.get_settings", lambda: disabled)
    client = _build_client(migrated_postgres, disabled)
    assert client.post(RESET_PATH, headers=ADMIN_HEADERS).status_code == 404


# --------------------------------------------------------------------------
# C. Reset
# --------------------------------------------------------------------------


def test_reset_restores_canonical_demo_state(
    demo_client: TestClient, demo_session: Session
) -> None:
    response = demo_client.post(RESET_PATH, headers=ADMIN_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["reset_performed"] is True
    assert body["organization_id"] == str(DEMO_ORGANIZATION_ID)
    assert body["recovery_case_count"] == RECOVERY_CASE_COUNT
    assert body["data_source"] == "SYNTHETIC_SIMULATION"

    count = demo_session.execute(
        select(RecoveryCase).where(RecoveryCase.organization_id == DEMO_ORGANIZATION_ID)
    ).all()
    assert len(count) == RECOVERY_CASE_COUNT


def test_reset_twice_is_deterministic(demo_client: TestClient, demo_session: Session) -> None:
    first = demo_client.post(RESET_PATH, headers=ADMIN_HEADERS).json()
    first_ids = _demo_case_ids(demo_session)

    second = demo_client.post(RESET_PATH, headers=ADMIN_HEADERS).json()
    second_ids = _demo_case_ids(demo_session)

    assert first == second
    assert first_ids == second_ids
    assert len(second_ids) == RECOVERY_CASE_COUNT


def _demo_case_ids(session: Session) -> list[uuid.UUID]:
    session.expire_all()
    rows = session.execute(
        select(RecoveryCase.id)
        .where(RecoveryCase.organization_id == DEMO_ORGANIZATION_ID)
        .order_by(RecoveryCase.id.asc())
    ).all()
    return [row[0] for row in rows]


def test_reset_does_not_accumulate_duplicates(
    demo_client: TestClient, demo_session: Session
) -> None:
    for _ in range(3):
        demo_client.post(RESET_PATH, headers=ADMIN_HEADERS)
    ids = _demo_case_ids(demo_session)
    assert len(ids) == len(set(ids)) == RECOVERY_CASE_COUNT


def test_reset_leaves_non_demo_data_untouched(
    demo_client: TestClient, demo_session: Session
) -> None:
    _seed_sentinel(demo_session)
    before_amount = demo_session.get(RecoveryCase, SENTINEL_CASE_ID).amount_at_risk_minor

    demo_client.post(RESET_PATH, headers=ADMIN_HEADERS)

    demo_session.expire_all()
    sentinel_org = demo_session.get(Organization, SENTINEL_ORG_ID)
    sentinel_case = demo_session.get(RecoveryCase, SENTINEL_CASE_ID)
    assert sentinel_org is not None
    assert sentinel_org.name == "Sentinel Non-Demo Org"
    assert sentinel_case is not None
    assert sentinel_case.amount_at_risk_minor == before_amount
    assert sentinel_case.organization_id == SENTINEL_ORG_ID


def test_reset_preserves_demo_merchant_policy(
    demo_client: TestClient, demo_session: Session
) -> None:
    demo_client.post(RESET_PATH, headers=ADMIN_HEADERS)
    demo_session.expire_all()
    policy = demo_session.execute(
        select(MerchantPolicy).where(MerchantPolicy.organization_id == DEMO_ORGANIZATION_ID)
    ).scalar_one_or_none()
    assert policy is not None


def test_reset_makes_no_provider_calls(
    demo_client: TestClient, provider_spy: ProviderSpy
) -> None:
    assert demo_client.post(RESET_PATH, headers=ADMIN_HEADERS).status_code == 200
    assert provider_spy.calls == []


def test_reset_rolls_back_on_failure(
    demo_client: TestClient,
    demo_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failure mid-reset must not publish a half-reset database."""
    before = _demo_case_ids(demo_session)
    assert len(before) == RECOVERY_CASE_COUNT

    def explode(*_args: object, **_kwargs: object):
        raise RuntimeError("injected seed failure")

    # Fail after the delete step, while persisting the new world. Seeding is
    # now two passes (world, then real analysis and the history derived from
    # it); failing in the first pass still has to roll the whole thing back.
    monkeypatch.setattr("app.demo.seed._persist_world", explode)

    response = demo_client.post(RESET_PATH, headers=ADMIN_HEADERS)
    assert response.status_code >= 500

    monkeypatch.undo()
    after = _demo_case_ids(demo_session)
    assert after == before


# --------------------------------------------------------------------------
# D. Batch
# --------------------------------------------------------------------------


POLICY_KEYS = {
    "number_of_cases",
    "amount_at_risk_minor",
    "expected_synthetic_recovered_minor",
    "realized_synthetic_recovered_minor",
    "realized_recovery_rate",
    "selected_intervention_count",
    "contact_action_count",
    "stop_count",
    "no_selection_count",
}


@pytest.fixture(scope="module")
def batch_client(
    migrated_postgres: Engine | None, demo_route_settings: Settings
) -> Generator[TestClient, None, None]:
    """Client for batch tests.

    The batch reads no business tables, so it needs no seeded demo data. A
    module-scoped client keeps the slow canonical evaluation from being repeated
    for every assertion.
    """
    if migrated_postgres is None:
        pytest.skip("PostgreSQL not available")
    client = _build_client(migrated_postgres, demo_route_settings)
    try:
        yield client
    finally:
        client.app.dependency_overrides.clear()


@pytest.fixture(scope="module")
def batch_body(batch_client: TestClient) -> dict:
    response = batch_client.post(BATCH_PATH, headers=ADMIN_HEADERS)
    assert response.status_code == 200
    return response.json()


def test_batch_returns_documented_schema(batch_body: dict) -> None:
    assert set(batch_body) == {
        "data_source",
        "evaluation_label",
        "scorer",
        "dataset",
        "revloop_model_policy",
        "naive_baseline_policy",
        "incremental_expected_recovered_minor",
        "incremental_realized_recovered_minor",
    }
    assert set(batch_body["revloop_model_policy"]) == POLICY_KEYS
    assert set(batch_body["naive_baseline_policy"]) == POLICY_KEYS
    assert set(batch_body["scorer"]) == {
        "model_version",
        "model_family",
        "feature_schema_version",
    }
    assert set(batch_body["dataset"]) == {
        "dataset_version",
        "seed",
        "split",
        "case_count",
    }


def test_batch_declares_synthetic_simulation_provenance(batch_body: dict) -> None:
    assert batch_body["data_source"] == "SYNTHETIC_SIMULATION"
    assert batch_body["evaluation_label"] == "SYNTHETIC POLICY SIMULATION"


def test_batch_reports_the_selected_model_as_the_scorer(batch_body: dict) -> None:
    """Provenance must name the model that actually produced the numbers."""
    assert batch_body["scorer"] == {
        "model_version": "lr-v1.0.0",
        "model_family": "logistic_regression",
        "feature_schema_version": "recovery_features_v1",
    }


def test_batch_reports_canonical_dataset_provenance(batch_body: dict) -> None:
    assert batch_body["dataset"]["dataset_version"] == "synthetic_recovery_v1"
    assert batch_body["dataset"]["seed"] == 20260901
    assert batch_body["dataset"]["split"] == "test"
    assert batch_body["dataset"]["case_count"] == DEMO_BATCH_CASE_COUNT


def test_batch_response_matches_the_canonical_evaluator(batch_body: dict) -> None:
    """The HTTP adapter must not alter the canonical numbers."""
    from app.demo.batch_service import to_response
    from app.demo.evaluation import run_canonical_batch

    direct = to_response(run_canonical_batch(DEMO_BATCH_CASE_COUNT))
    assert batch_body == direct.model_dump(mode="json")


def test_batch_is_deterministic_across_calls(batch_client: TestClient) -> None:
    first = batch_client.post(BATCH_PATH, headers=ADMIN_HEADERS).json()
    second = batch_client.post(BATCH_PATH, headers=ADMIN_HEADERS).json()
    assert first == second


def test_batch_makes_no_provider_calls(
    batch_client: TestClient, provider_spy: ProviderSpy
) -> None:
    """Mandatory provider zero-call regression at the adapter boundary."""
    response = batch_client.post(BATCH_PATH, headers=ADMIN_HEADERS)
    assert response.status_code == 200
    assert provider_spy.calls == []


def test_batch_makes_no_llm_or_outbound_http_calls(
    batch_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No Gemini/LLM traffic and no real outbound HTTP during evaluation.

    Only the real network transports are blocked. TestClient itself speaks httpx
    over an in-process ASGI transport, so patching `httpx.Client.send` would trap
    the test's own request rather than the code under test.
    """
    import httpx

    calls: list[str] = []

    def block(name: str):
        def _blocked(*_args: object, **_kwargs: object):
            calls.append(name)
            raise AssertionError(f"Batch must not perform {name}.")

        return _blocked

    monkeypatch.setattr(
        httpx.HTTPTransport, "handle_request", block("outbound HTTP"), raising=True
    )
    monkeypatch.setattr(
        httpx.AsyncHTTPTransport,
        "handle_async_request",
        block("outbound async HTTP"),
        raising=True,
    )

    assert batch_client.post(BATCH_PATH, headers=ADMIN_HEADERS).status_code == 200
    assert calls == []


def test_batch_performs_no_business_database_writes(
    batch_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy.orm import Session as OrmSession

    commits: list[str] = []
    original_commit = OrmSession.commit

    def spy_commit(self, *args: object, **kwargs: object):
        commits.append("commit")
        return original_commit(self, *args, **kwargs)

    monkeypatch.setattr(OrmSession, "commit", spy_commit, raising=True)
    assert batch_client.post(BATCH_PATH, headers=ADMIN_HEADERS).status_code == 200
    assert commits == []


def test_batch_fabricates_no_provider_evidence(batch_client: TestClient) -> None:
    raw = batch_client.post(BATCH_PATH, headers=ADMIN_HEADERS).text.lower()
    for fragment in (
        "razorpay",
        "rzp_",
        "pay_",
        "plink_",
        "signature",
        "webhook",
        "payment_link",
        "provider_payment_id",
        "razorpay_test",
        "https://",
    ):
        assert fragment not in raw, fragment


def test_batch_writes_nothing(demo_client: TestClient, demo_session: Session) -> None:
    """Repeated submissions cannot accumulate state because the batch is read-only."""
    before = _demo_case_ids(demo_session)
    for _ in range(2):
        demo_client.post(BATCH_PATH, headers=ADMIN_HEADERS)
    assert _demo_case_ids(demo_session) == before


def test_batch_evaluates_both_policies_over_the_same_cohort(batch_body: dict) -> None:
    revloop = batch_body["revloop_model_policy"]
    baseline = batch_body["naive_baseline_policy"]
    assert revloop["number_of_cases"] == baseline["number_of_cases"] == DEMO_BATCH_CASE_COUNT
    assert revloop["amount_at_risk_minor"] == baseline["amount_at_risk_minor"] > 0


def test_batch_incremental_arithmetic_is_consistent(batch_body: dict) -> None:
    assert batch_body["incremental_expected_recovered_minor"] == (
        batch_body["revloop_model_policy"]["expected_synthetic_recovered_minor"]
        - batch_body["naive_baseline_policy"]["expected_synthetic_recovered_minor"]
    )
    assert batch_body["incremental_realized_recovered_minor"] == (
        batch_body["revloop_model_policy"]["realized_synthetic_recovered_minor"]
        - batch_body["naive_baseline_policy"]["realized_synthetic_recovered_minor"]
    )


def test_batch_money_fields_are_integers(batch_body: dict) -> None:
    for policy in ("revloop_model_policy", "naive_baseline_policy"):
        for field in (
            "amount_at_risk_minor",
            "expected_synthetic_recovered_minor",
            "realized_synthetic_recovered_minor",
        ):
            assert isinstance(batch_body[policy][field], int), (policy, field)


def test_batch_recovery_rate_is_bounded(batch_body: dict) -> None:
    from decimal import Decimal

    for policy in ("revloop_model_policy", "naive_baseline_policy"):
        rate = Decimal(str(batch_body[policy]["realized_recovery_rate"]))
        assert Decimal(0) <= rate <= Decimal(1)


def test_batch_fails_closed_when_the_model_is_unavailable(
    batch_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fallback benchmark must never be published as the selected model."""
    from app.ml.service import ModelArtifactError

    def explode(*_args: object, **_kwargs: object):
        raise ModelArtifactError("injected artifact failure")

    monkeypatch.setattr("app.demo.evaluation.load_trusted_model_bundle", explode)
    response = batch_client.post(BATCH_PATH, headers=ADMIN_HEADERS)
    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "CANONICAL_EVALUATION_UNAVAILABLE"
    assert "revloop_model_policy" not in body
    assert "lr-v1.0.0" not in response.text


# --------------------------------------------------------------------------
# E. Reset / batch interaction
# --------------------------------------------------------------------------


def test_reset_batch_reset_batch_is_equivalent(
    demo_client: TestClient, demo_session: Session
) -> None:
    """The core demo invariant."""
    demo_client.post(RESET_PATH, headers=ADMIN_HEADERS)
    first_batch = demo_client.post(BATCH_PATH, headers=ADMIN_HEADERS).json()
    first_state = _demo_case_ids(demo_session)

    demo_client.post(RESET_PATH, headers=ADMIN_HEADERS)
    second_batch = demo_client.post(BATCH_PATH, headers=ADMIN_HEADERS).json()
    second_state = _demo_case_ids(demo_session)

    assert first_batch == second_batch
    assert first_state == second_state


def test_batch_is_independent_of_demo_database_state(
    demo_client: TestClient, demo_session: Session
) -> None:
    """The batch cohort is the canonical ML dataset, not the seeded UI demo rows."""
    before = demo_client.post(BATCH_PATH, headers=ADMIN_HEADERS).json()

    # Mutating seeded demo data must not move a single canonical metric.
    case_id = _demo_case_ids(demo_session)[0]
    case = demo_session.get(RecoveryCase, case_id)
    case.amount_at_risk_minor += 12_345
    demo_session.commit()

    after = demo_client.post(BATCH_PATH, headers=ADMIN_HEADERS).json()
    assert before == after
    assert after["dataset"]["case_count"] == DEMO_BATCH_CASE_COUNT


# --------------------------------------------------------------------------
# E. Evaluation (the Proof page's data source)
# --------------------------------------------------------------------------


def test_evaluation_is_readable_by_any_authenticated_role(
    demo_client: TestClient,
) -> None:
    """Reading a stored evaluation changes nothing, so it needs no ADMIN gate.

    Gating it would also imply the figures are privileged, which they are not --
    the whole point of the page is that a reviewer can check them.
    """
    for headers in (ADMIN_HEADERS, OPERATOR_HEADERS, ANALYST_HEADERS):
        response = demo_client.get("/api/v1/demo/evaluation", headers=headers)
        assert response.status_code == 200, headers
        body = response.json()
        assert body["evaluation"]["evaluation_label"] == "SYNTHETIC POLICY SIMULATION"
        assert body["evaluation"]["data_source"] == "SYNTHETIC_SIMULATION"


def test_evaluation_requires_authentication(demo_client: TestClient) -> None:
    assert demo_client.get("/api/v1/demo/evaluation").status_code == 401


def test_evaluation_reports_when_it_was_computed(demo_client: TestClient) -> None:
    """A stored figure must say when it was produced.

    Without this a reader cannot tell a live evaluation from a committed
    fixture, which is exactly the doubt the page exists to answer.
    """
    body = demo_client.get("/api/v1/demo/evaluation", headers=ADMIN_HEADERS).json()
    assert body["computed_at"]
    assert body["duration_seconds"] > 0
    assert body["recomputed"] is False


def test_recompute_requires_admin(demo_client: TestClient) -> None:
    """Not because it mutates business data -- it touches none -- but because it
    is several seconds of CPU that should not be triggerable by any caller."""
    for headers in (OPERATOR_HEADERS, ANALYST_HEADERS):
        response = demo_client.post(
            "/api/v1/demo/evaluation/recompute", headers=headers
        )
        assert response.status_code == 403, headers
        assert response.json()["error"]["code"] == "ROLE_NOT_ALLOWED"


def test_recompute_reproduces_identical_figures(demo_client: TestClient) -> None:
    """Determinism, over HTTP.

    This is the property the Recompute button demonstrates on stage: the
    timestamp moves, every number stays the same.
    """
    first = demo_client.get("/api/v1/demo/evaluation", headers=ADMIN_HEADERS).json()
    second = demo_client.post(
        "/api/v1/demo/evaluation/recompute", headers=ADMIN_HEADERS
    ).json()

    assert second["recomputed"] is True
    assert second["computed_at"] >= first["computed_at"]
    assert (
        second["evaluation"]["revloop_model_policy"]["realized_recovery_rate"]
        == first["evaluation"]["revloop_model_policy"]["realized_recovery_rate"]
    )
    assert (
        second["evaluation"]["incremental_realized_recovered_minor"]
        == first["evaluation"]["incremental_realized_recovered_minor"]
    )


def test_evaluation_makes_no_provider_calls(
    demo_client: TestClient,
    provider_spy: ProviderSpy,
) -> None:
    """An offline evaluation must stay offline."""
    assert (
        demo_client.get("/api/v1/demo/evaluation", headers=ADMIN_HEADERS).status_code
        == 200
    )
    assert provider_spy.calls == []
