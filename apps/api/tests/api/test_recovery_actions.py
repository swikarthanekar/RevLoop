"""Recovery action API tests (Prompt 16)."""

from __future__ import annotations

# ruff: noqa: E402
pytest_plugins = ["tests.recovery.conftest"]

import threading
import uuid
from collections.abc import Generator
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qs, unquote

import httpx
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.actions.service import RecoveryActionService
from app.api.routes.recovery_actions import get_recovery_action_service
from app.core.config import Settings, get_settings
from app.core.deps import get_db
from app.demo.constants import ALLOWED_ACTION_TYPES, AUTO_ACTION_LIMIT_MINOR, DEMO_ORGANIZATION_ID
from app.domain.enums import (
    RecoveryActionStatus,
    RecoveryActionType,
    RecoveryCaseStatus,
)
from app.main import create_app
from app.models.merchant_policy import MerchantPolicy
from app.models.recovery_action import RecoveryAction
from app.models.recovery_case import RecoveryCase
from app.models.recovery_outcome import RecoveryOutcome
from app.models.recovery_recommendation import RecoveryRecommendation
from tests.actions.helpers import payment_link_success_payload, setup_recommended_case
from tests.demo.conftest import postgres_available
from tests.integrations.razorpay.helpers import (
    build_webhook_payload,
    payment_entity,
    payment_link_entity,
    signed_request,
)
from tests.integrations.razorpay.razorpay_client_helpers import make_mock_client

pytestmark = pytest.mark.skipif(
    not postgres_available(),
    reason="PostgreSQL not available",
)

OPERATOR_HEADERS = {"Authorization": "Bearer dev-operator"}
ADMIN_HEADERS = {"Authorization": "Bearer dev-admin"}
ANALYST_HEADERS = {"Authorization": "Bearer dev-analyst"}


class MockPaymentLinkTransport:
    PostMode = str

    def __init__(
        self,
        *,
        fail_timeout: bool = False,
        post_mode: str = "success",
    ) -> None:
        self.post_count = 0
        self.get_count = 0
        self.fail_timeout = fail_timeout
        self.post_mode = post_mode
        self.last_reference: str | None = None
        self._links_by_reference: dict[str, dict] = {}
        self._lock = threading.Lock()

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method.upper() == "GET" and "payment_links" in path:
            with self._lock:
                self.get_count += 1
            query = request.url.query
            if isinstance(query, bytes):
                query = query.decode()
            params = parse_qs(query)
            refs = params.get("reference_id", [])
            if not refs:
                return httpx.Response(
                    200,
                    json={"entity": "collection", "count": 0, "items": []},
                )
            reference = unquote(refs[0])
            link = self._links_by_reference.get(reference)
            if link is None:
                return httpx.Response(200, json={"entity": "collection", "count": 0, "items": []})
            return httpx.Response(
                200,
                json={"entity": "collection", "count": 1, "items": [link]},
            )

        if request.method.upper() != "POST" or not path.endswith("/payment_links"):
            return httpx.Response(404)

        with self._lock:
            self.post_count += 1
        if self.fail_timeout:
            raise httpx.ReadTimeout("timeout")

        body = __import__("json").loads(request.content)
        reference = str(body["reference_id"])
        amount = int(body["amount"])
        currency = str(body["currency"])
        self.last_reference = reference

        if self.post_mode == "malformed_json":
            return httpx.Response(
                200,
                content=b"not-json",
                headers={"Content-Type": "application/json"},
            )
        if self.post_mode == "missing_id":
            return httpx.Response(
                200,
                json={"reference_id": reference, "amount": amount, "currency": currency},
            )
        if self.post_mode == "missing_reference":
            return httpx.Response(
                200,
                json={
                    "id": "plink_bad",
                    "amount": amount,
                    "currency": currency,
                    "status": "created",
                },
            )
        if self.post_mode == "reference_mismatch":
            return httpx.Response(
                200,
                json=payment_link_success_payload(
                    reference_id="wrong_ref",
                    amount=amount,
                    currency=currency,
                ),
            )
        if self.post_mode == "amount_mismatch":
            return httpx.Response(
                200,
                json=payment_link_success_payload(
                    reference_id=reference,
                    amount=amount + 1,
                    currency=currency,
                ),
            )
        if self.post_mode == "currency_mismatch":
            return httpx.Response(
                200,
                json=payment_link_success_payload(
                    reference_id=reference,
                    amount=amount,
                    currency="USD",
                ),
            )

        payload = payment_link_success_payload(
            reference_id=reference,
            amount=amount,
            currency=currency,
        )
        self._links_by_reference[reference] = payload
        return httpx.Response(200, json=payload)


@pytest.fixture(scope="session")
def action_settings(recovery_demo_settings) -> Settings:
    return recovery_demo_settings.model_copy(
        update={
            "razorpay_key_id": SecretStr("rzp_test_key"),
            "razorpay_key_secret": SecretStr("test_secret_value"),
            "razorpay_webhook_secret": SecretStr("dev-razorpay-webhook-secret"),
        }
    )


@pytest.fixture(scope="session")
def action_seeded_database(recovery_seeded_database):
    return recovery_seeded_database


@pytest.fixture
def mock_transport() -> MockPaymentLinkTransport:
    return MockPaymentLinkTransport()


@pytest.fixture
def action_client(
    action_seeded_database,
    action_settings,
    mock_transport,
) -> Generator[tuple[TestClient, MockPaymentLinkTransport], None, None]:
    transport = mock_transport
    razorpay = make_mock_client(transport.handler)

    app = create_app()

    def override_get_db() -> Generator[Session, None, None]:
        session = sessionmaker(bind=action_seeded_database, autoflush=False, autocommit=False)()
        try:
            yield session
        finally:
            session.close()

    def override_settings() -> Settings:
        return action_settings

    def service_override(db: Session = Depends(get_db)) -> RecoveryActionService:
        return RecoveryActionService(
            db,
            settings=action_settings,
            razorpay_client=razorpay,
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_recovery_action_service] = service_override
    client = TestClient(app, raise_server_exceptions=False)
    yield client, transport
    app.dependency_overrides.clear()


@pytest.fixture
def db_session(action_seeded_database) -> Generator[Session, None, None]:
    session = sessionmaker(bind=action_seeded_database, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def reset_persist_provider_success_hook() -> Generator[None, None, None]:
    RecoveryActionService.persist_provider_success_hook = None
    yield
    RecoveryActionService.persist_provider_success_hook = None


@pytest.fixture(autouse=True)
def reset_demo_policy(db_session) -> Generator[None, None, None]:
    policy = db_session.execute(
        select(MerchantPolicy).where(MerchantPolicy.organization_id == DEMO_ORGANIZATION_ID)
    ).scalar_one()
    policy.allowed_action_types = list(ALLOWED_ACTION_TYPES)
    policy.auto_action_limit_minor = AUTO_ACTION_LIMIT_MINOR
    db_session.commit()
    yield


def _action_snapshot(db_session: Session, case_id: uuid.UUID) -> dict[str, object]:
    action = db_session.execute(
        select(RecoveryAction).where(RecoveryAction.case_id == case_id)
    ).scalar_one()
    case = db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == case_id)
    ).scalar_one()
    return {
        "case_status": case.status,
        "action_status": action.status,
        "idempotency_key": action.idempotency_key,
        "attempt_number": action.attempt_number,
        "provider_reference": action.provider_reference,
        "provider_link_id": action.metadata_.get("provider_payment_link_id"),
    }


def _fire_payment_link_paid_webhook(
    *,
    action_settings: Settings,
    action_seeded_database,
    reference: str,
    amount: int,
    event_id: str,
) -> None:
    webhook_app = create_app()

    def override_get_db() -> Generator[Session, None, None]:
        session = sessionmaker(bind=action_seeded_database, autoflush=False, autocommit=False)()
        try:
            yield session
        finally:
            session.close()

    webhook_app.dependency_overrides[get_db] = override_get_db
    webhook_app.dependency_overrides[get_settings] = lambda: action_settings
    webhook_client = TestClient(webhook_app, raise_server_exceptions=False)
    link = payment_link_entity(reference_id=reference, amount=amount)
    payment = payment_entity(payment_id=f"pay_{event_id}", amount=amount, status="captured")
    payload = build_webhook_payload("payment_link.paid", payment=payment, payment_link=link)
    raw_body, _, _, headers = signed_request(payload, event_id=event_id)
    response = webhook_client.post("/api/v1/webhooks/razorpay", content=raw_body, headers=headers)
    assert response.status_code == 204
    webhook_app.dependency_overrides.clear()


def _execute_action(
    client: TestClient,
    case_id: uuid.UUID,
    run_id: uuid.UUID,
    action_type: RecoveryActionType = RecoveryActionType.CREATE_PAYMENT_LINK,
) -> Any:
    return client.post(
        f"/api/v1/recovery-cases/{case_id}/actions",
        headers=OPERATOR_HEADERS,
        json={"analysis_run_id": str(run_id), "action_type": action_type.value},
    )


def test_create_payment_link_success(action_client, db_session) -> None:
    client, transport = action_client
    case, run_id, _ = setup_recommended_case(db_session)
    response = _execute_action(client, case.id, run_id)
    assert response.status_code == 201
    payload = response.json()
    assert payload["case_status"] == RecoveryCaseStatus.WAITING_FOR_OUTCOME.value
    assert payload["action"]["status"] == RecoveryActionStatus.SUCCEEDED.value
    assert payload["action"]["provider_reference"].startswith("rl_")
    assert payload["customer_action"]["type"] == "PAYMENT_LINK"
    assert transport.post_count == 1
    assert db_session.execute(
        select(func.count()).select_from(RecoveryOutcome).where(RecoveryOutcome.case_id == case.id)
    ).scalar_one() == 0


def test_sequential_double_click_one_post(action_client, db_session) -> None:
    client, transport = action_client
    case, run_id, _ = setup_recommended_case(db_session)
    first = _execute_action(client, case.id, run_id)
    second = _execute_action(client, case.id, run_id)
    assert first.status_code == 201
    assert second.status_code == 201
    assert transport.post_count == 1
    assert db_session.execute(
        select(func.count()).select_from(RecoveryAction).where(RecoveryAction.case_id == case.id)
    ).scalar_one() == 1


def test_concurrent_double_click_one_post(action_seeded_database, action_settings) -> None:
    transport = MockPaymentLinkTransport()
    case_id_holder: dict[str, uuid.UUID] = {}
    run_id_holder: dict[str, uuid.UUID] = {}
    setup_session = sessionmaker(bind=action_seeded_database, autoflush=False, autocommit=False)()
    try:
        case, run_id, _ = setup_recommended_case(setup_session)
        case_id_holder["id"] = case.id
        run_id_holder["id"] = run_id
    finally:
        setup_session.close()

    results: list[Any] = []
    errors: list[Exception] = []

    def worker() -> None:
        app = create_app()
        transport_local = transport
        razorpay = make_mock_client(transport_local.handler)

        def override_get_db() -> Generator[Session, None, None]:
            session = sessionmaker(
                bind=action_seeded_database,
                autoflush=False,
                autocommit=False,
            )()
            try:
                yield session
            finally:
                session.close()

        def override_settings() -> Settings:
            return action_settings

        def service_override(db: Session = Depends(get_db)) -> RecoveryActionService:
            return RecoveryActionService(
                db,
                settings=action_settings,
                razorpay_client=razorpay,
            )

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_settings] = override_settings
        app.dependency_overrides[get_recovery_action_service] = service_override
        test_client = TestClient(app, raise_server_exceptions=False)
        try:
            response = _execute_action(test_client, case_id_holder["id"], run_id_holder["id"])
            results.append(response)
        except Exception as exc:  # pragma: no cover
            errors.append(exc)
        finally:
            app.dependency_overrides.clear()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
    assert len(results) == 2
    assert all(response.status_code == 201 for response in results)
    assert transport.post_count == 1
    verify = sessionmaker(bind=action_seeded_database, autoflush=False, autocommit=False)()
    try:
        assert verify.execute(
            select(func.count()).select_from(RecoveryAction).where(
                RecoveryAction.case_id == case_id_holder["id"]
            )
        ).scalar_one() == 1
    finally:
        verify.close()


def test_approval_required_zero_provider_posts(action_client, db_session) -> None:
    client, transport = action_client
    case, run_id, _ = setup_recommended_case(db_session, amount_at_risk_minor=2_000_000)
    response = _execute_action(client, case.id, run_id)
    assert response.status_code == 201
    payload = response.json()
    assert payload["case_status"] == RecoveryCaseStatus.AWAITING_APPROVAL.value
    assert payload["action"]["status"] == RecoveryActionStatus.PENDING_APPROVAL.value
    assert payload["customer_action"] is None
    assert transport.post_count == 0


def test_approve_triggers_single_post(action_client, db_session) -> None:
    client, transport = action_client
    case, run_id, _ = setup_recommended_case(db_session, amount_at_risk_minor=2_000_000)
    create = _execute_action(client, case.id, run_id)
    action_id = create.json()["action"]["id"]
    db_session.expire_all()
    case_row = db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == case.id)
    ).scalar_one()
    approve = client.post(
        f"/api/v1/recovery-actions/{action_id}/approve",
        headers=ADMIN_HEADERS,
        json={"expected_case_version": case_row.version},
    )
    assert approve.status_code == 200
    assert approve.json()["case_status"] == RecoveryCaseStatus.WAITING_FOR_OUTCOME.value
    assert transport.post_count == 1


def test_stale_recommendation_rejected(action_client, db_session) -> None:
    client, transport = action_client
    case, stale_run_id, _ = setup_recommended_case(db_session)
    new_run_id = uuid.uuid4()
    case.current_analysis_run_id = new_run_id
    db_session.commit()
    response = _execute_action(client, case.id, stale_run_id)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ACTION_NOT_IN_ANALYSIS"
    assert transport.post_count == 0


def test_policy_allowlist_blocks_action(action_client, db_session) -> None:
    client, transport = action_client
    case, run_id, _ = setup_recommended_case(db_session)
    policy = db_session.execute(
        select(MerchantPolicy).where(MerchantPolicy.organization_id == DEMO_ORGANIZATION_ID)
    ).scalar_one()
    policy.allowed_action_types = [RecoveryActionType.WAIT.value, RecoveryActionType.STOP.value]
    db_session.commit()
    response = _execute_action(client, case.id, run_id)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ACTION_BLOCKED_BY_POLICY"
    assert transport.post_count == 0


def test_wait_schedules_without_provider(action_client, db_session) -> None:
    client, transport = action_client
    case, run_id, _ = setup_recommended_case(
        db_session,
        action_type=RecoveryActionType.WAIT,
    )
    response = _execute_action(client, case.id, run_id, RecoveryActionType.WAIT)
    assert response.status_code == 201
    payload = response.json()
    assert payload["case_status"] == RecoveryCaseStatus.SCHEDULED.value
    assert payload["action"]["status"] == RecoveryActionStatus.SCHEDULED.value
    assert payload["action"]["scheduled_for"] is not None
    assert transport.post_count == 0


def test_stop_without_provider(action_client, db_session) -> None:
    client, transport = action_client
    case, run_id, _ = setup_recommended_case(
        db_session,
        action_type=RecoveryActionType.STOP,
    )
    response = _execute_action(client, case.id, run_id, RecoveryActionType.STOP)
    assert response.status_code == 201
    assert response.json()["case_status"] == RecoveryCaseStatus.STOPPED.value
    assert transport.post_count == 0


def test_terminal_case_blocks_action(action_client, db_session) -> None:
    client, transport = action_client
    case, run_id, _ = setup_recommended_case(db_session)
    case.status = RecoveryCaseStatus.RECOVERED.value
    db_session.commit()
    response = _execute_action(client, case.id, run_id)
    assert response.status_code == 409
    assert transport.post_count == 0


def test_provider_timeout_unknown(action_seeded_database, action_settings) -> None:
    transport = MockPaymentLinkTransport(fail_timeout=True)
    db_session = sessionmaker(bind=action_seeded_database, autoflush=False, autocommit=False)()
    case, run_id, _ = setup_recommended_case(db_session)
    case_id = case.id
    db_session.close()

    app = create_app()
    razorpay = make_mock_client(transport.handler)

    def override_get_db() -> Generator[Session, None, None]:
        session = sessionmaker(bind=action_seeded_database, autoflush=False, autocommit=False)()
        try:
            yield session
        finally:
            session.close()

    def override_settings() -> Settings:
        return action_settings

    def service_override(db: Session = Depends(get_db)) -> RecoveryActionService:
        return RecoveryActionService(
            db,
            settings=action_settings,
            razorpay_client=razorpay,
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_recovery_action_service] = service_override
    test_client = TestClient(app, raise_server_exceptions=False)
    response = _execute_action(test_client, case_id, run_id)
    assert response.status_code == 201
    payload = response.json()
    assert payload["action"]["status"] == RecoveryActionStatus.UNKNOWN.value
    assert payload["case_status"] == RecoveryCaseStatus.WAITING_FOR_OUTCOME.value
    assert transport.post_count == 1
    retry = _execute_action(test_client, case_id, run_id)
    assert retry.status_code == 201
    assert transport.post_count == 1
    app.dependency_overrides.clear()


def test_analyst_cannot_execute(action_client, db_session) -> None:
    client, _ = action_client
    case, run_id, _ = setup_recommended_case(db_session)
    response = client.post(
        f"/api/v1/recovery-cases/{case.id}/actions",
        headers=ANALYST_HEADERS,
        json={"analysis_run_id": str(run_id), "action_type": "CREATE_PAYMENT_LINK"},
    )
    assert response.status_code == 403


def test_request_tampering_rejects_extra_fields(action_client, db_session) -> None:
    client, _ = action_client
    case, run_id, _ = setup_recommended_case(db_session)
    response = client.post(
        f"/api/v1/recovery-cases/{case.id}/actions",
        headers=OPERATOR_HEADERS,
        json={
            "analysis_run_id": str(run_id),
            "action_type": "CREATE_PAYMENT_LINK",
            "amount_minor": 1,
            "requires_approval": False,
        },
    )
    assert response.status_code == 422


def test_payment_link_paid_cross_milestone(
    action_client,
    db_session,
    action_settings,
    action_seeded_database,
) -> None:
    client, transport = action_client
    case, run_id, _ = setup_recommended_case(db_session)
    create = _execute_action(client, case.id, run_id)
    assert create.status_code == 201
    reference = create.json()["action"]["provider_reference"]
    assert reference == transport.last_reference

    webhook_app = create_app()

    def override_get_db() -> Generator[Session, None, None]:
        session = sessionmaker(bind=action_seeded_database, autoflush=False, autocommit=False)()
        try:
            yield session
        finally:
            session.close()

    def override_settings() -> Settings:
        return action_settings

    webhook_app.dependency_overrides[get_db] = override_get_db
    webhook_app.dependency_overrides[get_settings] = override_settings
    webhook_client = TestClient(webhook_app, raise_server_exceptions=False)

    link = payment_link_entity(reference_id=reference, amount=case.amount_at_risk_minor)
    payment = payment_entity(
        payment_id="pay_cross_milestone",
        amount=case.amount_at_risk_minor,
        status="captured",
    )
    payload = build_webhook_payload("payment_link.paid", payment=payment, payment_link=link)
    raw_body, _, _, headers = signed_request(payload, event_id="evt_cross_milestone")
    webhook_response = webhook_client.post(
        "/api/v1/webhooks/razorpay",
        content=raw_body,
        headers=headers,
    )
    assert webhook_response.status_code == 204
    db_session.expire_all()
    refreshed = db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == case.id)
    ).scalar_one()
    assert refreshed.status == RecoveryCaseStatus.RECOVERED.value
    assert db_session.execute(
        select(func.count()).select_from(RecoveryOutcome).where(RecoveryOutcome.case_id == case.id)
    ).scalar_one() == 1
    webhook_app.dependency_overrides.clear()


def test_escalate_to_human_requires_approval_and_never_calls_the_provider(
    action_client, db_session
) -> None:
    """ESCALATE_TO_HUMAN always requires approval (the manual-contact
    policy applies to it unconditionally), and approving it must never
    invoke the payment provider -- there is no payment link for a human
    handoff. Answers "the bar"'s compliant-escalation requirement: a case
    the model recommends escalating is a real, clickable, auditable action,
    not a dead end."""
    client, transport = action_client
    case, run_id, _ = setup_recommended_case(
        db_session, action_type=RecoveryActionType.ESCALATE_TO_HUMAN
    )
    create = _execute_action(
        client, case.id, run_id, action_type=RecoveryActionType.ESCALATE_TO_HUMAN
    )
    assert create.status_code == 201
    payload = create.json()
    assert payload["case_status"] == RecoveryCaseStatus.AWAITING_APPROVAL.value
    assert payload["action"]["status"] == RecoveryActionStatus.PENDING_APPROVAL.value
    assert payload["action"]["action_type"] == RecoveryActionType.ESCALATE_TO_HUMAN.value
    assert payload["customer_action"] is None
    assert transport.post_count == 0

    action_id = payload["action"]["id"]
    db_session.expire_all()
    case_row = db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == case.id)
    ).scalar_one()
    approve = client.post(
        f"/api/v1/recovery-actions/{action_id}/approve",
        headers=ADMIN_HEADERS,
        json={"expected_case_version": case_row.version},
    )
    assert approve.status_code == 200
    assert approve.json()["case_status"] == RecoveryCaseStatus.WAITING_FOR_OUTCOME.value
    assert approve.json()["action_status"] == RecoveryActionStatus.SUCCEEDED.value
    assert transport.post_count == 0

    db_session.expire_all()
    action_row = db_session.execute(
        select(RecoveryAction).where(RecoveryAction.id == action_id)
    ).scalar_one()
    assert action_row.action_type == RecoveryActionType.ESCALATE_TO_HUMAN.value
    assert action_row.metadata_.get("escalation_reason")


def test_request_alternate_payment_method_executes_immediately(
    action_client, db_session
) -> None:
    """REQUEST_ALTERNATE_PAYMENT_METHOD is executable (Prompt 27 hardening):
    it shares CREATE_PAYMENT_LINK's Payment Link mechanism (a Standard
    Payment Link's checkout page already lets the customer pick any
    available method), but its own action_type label must be preserved end
    to end -- not silently rewritten -- so the recommendation and the
    resulting action stay consistent everywhere that reads them."""
    client, transport = action_client
    case, run_id, _ = setup_recommended_case(
        db_session, action_type=RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD
    )
    response = _execute_action(
        client, case.id, run_id, action_type=RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["case_status"] == RecoveryCaseStatus.WAITING_FOR_OUTCOME.value
    assert payload["action"]["status"] == RecoveryActionStatus.SUCCEEDED.value
    assert (
        payload["action"]["action_type"]
        == RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD.value
    )
    assert payload["action"]["provider_reference"].startswith("rl_")
    assert payload["customer_action"]["type"] == "PAYMENT_LINK"
    assert transport.post_count == 1


def test_request_alternate_payment_method_requires_approval_then_executes(
    action_client, db_session
) -> None:
    client, transport = action_client
    case, run_id, _ = setup_recommended_case(
        db_session,
        action_type=RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD,
        amount_at_risk_minor=2_000_000,
    )
    create = _execute_action(
        client, case.id, run_id, action_type=RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD
    )
    assert create.status_code == 201
    payload = create.json()
    assert payload["case_status"] == RecoveryCaseStatus.AWAITING_APPROVAL.value
    assert payload["action"]["status"] == RecoveryActionStatus.PENDING_APPROVAL.value
    assert payload["customer_action"] is None
    assert transport.post_count == 0

    action_id = payload["action"]["id"]
    db_session.expire_all()
    case_row = db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == case.id)
    ).scalar_one()
    approve = client.post(
        f"/api/v1/recovery-actions/{action_id}/approve",
        headers=ADMIN_HEADERS,
        json={"expected_case_version": case_row.version},
    )
    assert approve.status_code == 200
    assert approve.json()["case_status"] == RecoveryCaseStatus.WAITING_FOR_OUTCOME.value
    assert transport.post_count == 1


def test_approved_payment_link_url_visible_on_case_detail(
    action_client, db_session
) -> None:
    """Before this fix, a Payment Link created via approve_action (the
    high-value / requires-approval path) was never returned anywhere the
    frontend could read: CreateRecoveryActionResponse.customer_action is
    only populated on the immediate-execute response, and
    ApproveRecoveryActionResponse never carried it at all. An operator who
    approved a high-value case had no way to see the link through the app.
    GET case detail's latest_action.customer_action must carry it, since the
    frontend already refetches case detail after every mutation."""
    client, transport = action_client
    case, run_id, _ = setup_recommended_case(db_session, amount_at_risk_minor=2_000_000)
    create = _execute_action(client, case.id, run_id)
    action_id = create.json()["action"]["id"]

    detail_before_approval = client.get(
        f"/api/v1/recovery-cases/{case.id}", headers=OPERATOR_HEADERS
    )
    assert detail_before_approval.status_code == 200
    assert detail_before_approval.json()["latest_action"]["customer_action"] is None

    db_session.expire_all()
    case_row = db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == case.id)
    ).scalar_one()
    approve = client.post(
        f"/api/v1/recovery-actions/{action_id}/approve",
        headers=ADMIN_HEADERS,
        json={"expected_case_version": case_row.version},
    )
    assert approve.status_code == 200
    assert transport.post_count == 1

    detail_after_approval = client.get(
        f"/api/v1/recovery-cases/{case.id}", headers=OPERATOR_HEADERS
    )
    assert detail_after_approval.status_code == 200
    customer_action = detail_after_approval.json()["latest_action"]["customer_action"]
    assert customer_action == {"type": "PAYMENT_LINK", "url": "https://rzp.io/i/testlink"}


def test_request_alternate_payment_method_payment_link_paid_resolves_case(
    action_client,
    db_session,
    action_settings,
    action_seeded_database,
) -> None:
    """The payment_link.paid webhook must resolve an action recorded under
    REQUEST_ALTERNATE_PAYMENT_METHOD, not only CREATE_PAYMENT_LINK -- before
    this fix, RecoveryAction.action_type was never rewritten but the webhook
    lookup only matched the literal CREATE_PAYMENT_LINK value, so a genuinely
    recovered payment would have stayed WAITING_FOR_OUTCOME forever."""
    client, transport = action_client
    case, run_id, _ = setup_recommended_case(
        db_session, action_type=RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD
    )
    create = _execute_action(
        client, case.id, run_id, action_type=RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD
    )
    assert create.status_code == 201
    reference = create.json()["action"]["provider_reference"]
    assert reference == transport.last_reference

    _fire_payment_link_paid_webhook(
        action_settings=action_settings,
        action_seeded_database=action_seeded_database,
        reference=reference,
        amount=case.amount_at_risk_minor,
        event_id="evt_alt_method_paid",
    )
    db_session.expire_all()
    refreshed = db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == case.id)
    ).scalar_one()
    assert refreshed.status == RecoveryCaseStatus.RECOVERED.value
    assert db_session.execute(
        select(func.count()).select_from(RecoveryOutcome).where(RecoveryOutcome.case_id == case.id)
    ).scalar_one() == 1


def test_payment_link_mechanism_actions_block_each_other(action_client, db_session) -> None:
    """A REQUEST_ALTERNATE_PAYMENT_METHOD action in flight must block a
    CREATE_PAYMENT_LINK attempt for the same case, and vice versa: both use
    the identical Payment Link creation call and must not run concurrently.

    Reproduces the realistic shape of this scenario: an earlier payment-link
    action is still PENDING_APPROVAL (e.g. left un-reconciled) while the case
    has separately been brought back to RECOMMENDED for a new attempt -- not
    a second click while still AWAITING_APPROVAL, which _ensure_case_actionable
    already rejects earlier and independently of this check."""
    client, transport = action_client
    case, run_id_a, _ = setup_recommended_case(
        db_session,
        action_type=RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD,
        amount_at_risk_minor=2_000_000,
    )
    first = _execute_action(
        client, case.id, run_id_a, action_type=RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD
    )
    assert first.status_code == 201
    assert first.json()["case_status"] == RecoveryCaseStatus.AWAITING_APPROVAL.value

    run_id_b = uuid.uuid4()
    db_session.expire_all()
    case_row = db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == case.id)
    ).scalar_one()
    case_row.status = RecoveryCaseStatus.RECOMMENDED.value
    case_row.current_analysis_run_id = run_id_b
    db_session.add(
        RecoveryRecommendation(
            organization_id=case_row.organization_id,
            case_id=case_row.id,
            analysis_run_id=run_id_b,
            action_type=RecoveryActionType.CREATE_PAYMENT_LINK.value,
            rank=1,
            success_probability=Decimal("0.720000"),
            expected_recovered_minor=case_row.amount_at_risk_minor,
            expected_value_minor=350000,
            confidence=Decimal("0.810000"),
            policy_eligible=True,
            requires_approval=False,
            policy_reasons=[],
            factors=[],
            model_version="test-model",
            feature_schema_version="recovery_features_v1",
        )
    )
    db_session.commit()

    second = _execute_action(
        client, case.id, run_id_b, action_type=RecoveryActionType.CREATE_PAYMENT_LINK
    )
    # Caught by the policy layer's EQUIVALENT_ACTION_IN_FLIGHT check first
    # (_build_policy_context also treats every PAYMENT_LINK_MECHANISM_ACTIONS
    # member as in flight while one is blocking); the harder ActionConflictError
    # a few lines later in create_case_action is defense-in-depth for a path
    # this policy check doesn't cover.
    assert second.status_code == 422
    body = second.json()
    assert body["error"]["code"] == "ACTION_BLOCKED_BY_POLICY"
    assert "EQUIVALENT_ACTION_IN_FLIGHT" in body["error"]["details"]["reasons"]
    assert transport.post_count == 0


def test_reject_reanalyze_immediate_rerank(action_client, db_session) -> None:
    client, transport = action_client
    case, original_run_id, original_recommendation = setup_recommended_case(
        db_session,
        amount_at_risk_minor=2_000_000,
    )
    create = _execute_action(client, case.id, original_run_id)
    action_id = create.json()["action"]["id"]
    reject = client.post(
        f"/api/v1/recovery-actions/{action_id}/reject",
        headers=ADMIN_HEADERS,
        json={"reason": "Manual review preferred", "reanalyze": True},
    )
    assert reject.status_code == 200
    payload = reject.json()
    assert payload["action_status"] == RecoveryActionStatus.CANCELLED.value
    assert payload["case_status"] == RecoveryCaseStatus.RECOMMENDED.value
    assert transport.post_count == 0

    db_session.expire_all()
    cancelled = db_session.execute(
        select(RecoveryAction).where(RecoveryAction.id == uuid.UUID(action_id))
    ).scalar_one()
    assert cancelled.status == RecoveryActionStatus.CANCELLED.value

    old_recommendation = db_session.execute(
        select(RecoveryRecommendation).where(
            RecoveryRecommendation.id == original_recommendation.id
        )
    ).scalar_one()
    assert old_recommendation.analysis_run_id == original_run_id

    refreshed_case = db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == case.id)
    ).scalar_one()
    assert refreshed_case.current_analysis_run_id != original_run_id
    new_recommendation = db_session.execute(
        select(RecoveryRecommendation).where(
            RecoveryRecommendation.case_id == case.id,
            RecoveryRecommendation.analysis_run_id == refreshed_case.current_analysis_run_id,
            RecoveryRecommendation.rank == 1,
        )
    ).scalar_one()
    assert new_recommendation.action_type != RecoveryActionType.CREATE_PAYMENT_LINK.value


def test_reject_stop_no_reanalysis(action_client, db_session) -> None:
    client, transport = action_client
    case, run_id, _ = setup_recommended_case(db_session, amount_at_risk_minor=2_000_000)
    create = _execute_action(client, case.id, run_id)
    action_id = create.json()["action"]["id"]
    reject = client.post(
        f"/api/v1/recovery-actions/{action_id}/reject",
        headers=ADMIN_HEADERS,
        json={"reason": "Do not proceed", "reanalyze": False},
    )
    assert reject.status_code == 200
    assert reject.json()["case_status"] == RecoveryCaseStatus.STOPPED.value
    assert reject.json()["action_status"] == RecoveryActionStatus.CANCELLED.value
    assert transport.post_count == 0


def test_reject_pending_action(action_client, db_session) -> None:
    client, transport = action_client
    case, run_id, _ = setup_recommended_case(db_session, amount_at_risk_minor=2_000_000)
    create = _execute_action(client, case.id, run_id)
    action_id = create.json()["action"]["id"]
    reject = client.post(
        f"/api/v1/recovery-actions/{action_id}/reject",
        headers=ADMIN_HEADERS,
        json={"reason": "Manual review preferred", "reanalyze": True},
    )
    assert reject.status_code == 200
    assert reject.json()["case_status"] == RecoveryCaseStatus.RECOMMENDED.value
    assert transport.post_count == 0


def test_operator_cannot_approve_or_reject(action_client, db_session) -> None:
    client, transport = action_client
    case, run_id, _ = setup_recommended_case(db_session, amount_at_risk_minor=2_000_000)
    create = _execute_action(client, case.id, run_id)
    action_id = create.json()["action"]["id"]
    db_session.expire_all()
    version = db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == case.id)
    ).scalar_one().version
    approve = client.post(
        f"/api/v1/recovery-actions/{action_id}/approve",
        headers=OPERATOR_HEADERS,
        json={"expected_case_version": version},
    )
    reject = client.post(
        f"/api/v1/recovery-actions/{action_id}/reject",
        headers=OPERATOR_HEADERS,
        json={"reason": "nope", "reanalyze": False},
    )
    assert approve.status_code == 403
    assert reject.status_code == 403
    assert transport.post_count == 0


@pytest.mark.parametrize(
    "terminal_status",
    [RecoveryCaseStatus.RECOVERED, RecoveryCaseStatus.FAILED, RecoveryCaseStatus.STOPPED],
)
def test_approve_after_terminal_case_conflict(
    action_client,
    db_session,
    action_settings,
    action_seeded_database,
    terminal_status: RecoveryCaseStatus,
) -> None:
    client, transport = action_client
    case, run_id, _ = setup_recommended_case(db_session, amount_at_risk_minor=2_000_000)
    create = _execute_action(client, case.id, run_id)
    action_id = create.json()["action"]["id"]
    reference = create.json()["action"]["provider_reference"]
    db_session.expire_all()
    version = db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == case.id)
    ).scalar_one().version

    if terminal_status == RecoveryCaseStatus.RECOVERED:
        _fire_payment_link_paid_webhook(
            action_settings=action_settings,
            action_seeded_database=action_seeded_database,
            reference=reference,
            amount=case.amount_at_risk_minor,
            event_id=f"evt_terminal_{terminal_status.value}",
        )
    else:
        case_row = db_session.execute(
            select(RecoveryCase).where(RecoveryCase.id == case.id)
        ).scalar_one()
        case_row.status = terminal_status.value
        db_session.commit()

    db_session.expire_all()
    approve = client.post(
        f"/api/v1/recovery-actions/{action_id}/approve",
        headers=ADMIN_HEADERS,
        json={"expected_case_version": version},
    )
    assert approve.status_code == 409
    assert approve.json()["error"]["code"] == "CASE_ALREADY_RESOLVED"
    assert transport.post_count == 0
    assert db_session.execute(
        select(func.count()).select_from(RecoveryAction).where(RecoveryAction.case_id == case.id)
    ).scalar_one() == 1
    refreshed = db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == case.id)
    ).scalar_one()
    assert refreshed.status == terminal_status.value


def test_post_provider_db_failure_retry_reconciles(
    action_seeded_database,
    action_settings,
    monkeypatch,
) -> None:
    transport = MockPaymentLinkTransport()
    setup = sessionmaker(bind=action_seeded_database, autoflush=False, autocommit=False)()
    case, run_id, _ = setup_recommended_case(setup)
    case_id = case.id
    setup.close()

    t0: dict[str, object] = {}

    from app.integrations.razorpay import payment_links as payment_links_module

    real_create = payment_links_module.create_payment_link

    def capture_t0_then_create(*args, **kwargs):
        verify = sessionmaker(bind=action_seeded_database, autoflush=False, autocommit=False)()
        try:
            t0.update(_action_snapshot(verify, case_id))
            t0["post_count"] = transport.post_count
            t0["get_count"] = transport.get_count
        finally:
            verify.close()
        return real_create(*args, **kwargs)

    monkeypatch.setattr("app.actions.service.create_payment_link", capture_t0_then_create)

    def _fail_persist(_action, _case, _result) -> None:
        raise RuntimeError("simulated persistence failure")

    RecoveryActionService.persist_provider_success_hook = _fail_persist

    app = create_app()
    razorpay = make_mock_client(transport.handler)

    def override_get_db() -> Generator[Session, None, None]:
        session = sessionmaker(bind=action_seeded_database, autoflush=False, autocommit=False)()
        try:
            yield session
        finally:
            session.close()

    def service_override(db: Session = Depends(get_db)) -> RecoveryActionService:
        return RecoveryActionService(db, settings=action_settings, razorpay_client=razorpay)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: action_settings
    app.dependency_overrides[get_recovery_action_service] = service_override
    test_client = TestClient(app, raise_server_exceptions=False)

    first = _execute_action(test_client, case_id, run_id)
    assert first.status_code == 500
    assert transport.post_count == 1
    assert transport.get_count == 0

    verify = sessionmaker(bind=action_seeded_database, autoflush=False, autocommit=False)()
    try:
        t1 = _action_snapshot(verify, case_id)
        t1["post_count"] = transport.post_count
        t1["get_count"] = transport.get_count
    finally:
        verify.close()

    RecoveryActionService.persist_provider_success_hook = None

    retry = _execute_action(test_client, case_id, run_id)
    assert retry.status_code == 201
    assert transport.post_count == 1
    assert transport.get_count >= 1

    verify = sessionmaker(bind=action_seeded_database, autoflush=False, autocommit=False)()
    try:
        t2 = _action_snapshot(verify, case_id)
        t2["post_count"] = transport.post_count
        t2["get_count"] = transport.get_count
        payload = retry.json()
        assert payload["case_status"] == RecoveryCaseStatus.WAITING_FOR_OUTCOME.value
        assert payload["action"]["status"] == RecoveryActionStatus.SUCCEEDED.value
        assert t2["provider_link_id"] is not None
        assert t2["attempt_number"] == t0["attempt_number"]
        assert t2["provider_reference"] == t0["provider_reference"]
        assert t2["idempotency_key"] == t0["idempotency_key"]
        assert (
            verify.execute(
                select(func.count()).select_from(RecoveryAction).where(
                    RecoveryAction.case_id == case_id
                )
            ).scalar_one()
            == 1
        )
    finally:
        verify.close()

    assert t0["post_count"] == 0
    assert t0["case_status"] == RecoveryCaseStatus.EXECUTING.value
    assert t0["provider_reference"] is not None
    assert t1["post_count"] == 1
    assert t1["case_status"] in {
        RecoveryCaseStatus.EXECUTING.value,
        RecoveryCaseStatus.WAITING_FOR_OUTCOME.value,
    }
    assert t1["provider_link_id"] is None
    assert t2["post_count"] == 1

    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "post_mode",
    ["malformed_json", "missing_id", "missing_reference"],
)
def test_malformed_provider_2xx_unknown_then_retry_no_second_post(
    action_seeded_database,
    action_settings,
    post_mode: str,
) -> None:
    transport = MockPaymentLinkTransport(post_mode=post_mode)
    setup = sessionmaker(bind=action_seeded_database, autoflush=False, autocommit=False)()
    case, run_id, _ = setup_recommended_case(setup)
    case_id = case.id
    setup.close()

    app = create_app()
    razorpay = make_mock_client(transport.handler)

    def override_get_db() -> Generator[Session, None, None]:
        session = sessionmaker(bind=action_seeded_database, autoflush=False, autocommit=False)()
        try:
            yield session
        finally:
            session.close()

    def service_override(db: Session = Depends(get_db)) -> RecoveryActionService:
        return RecoveryActionService(db, settings=action_settings, razorpay_client=razorpay)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: action_settings
    app.dependency_overrides[get_recovery_action_service] = service_override
    test_client = TestClient(app, raise_server_exceptions=False)

    first = _execute_action(test_client, case_id, run_id)
    assert first.status_code == 201
    assert first.json()["action"]["status"] == RecoveryActionStatus.UNKNOWN.value
    assert first.json()["case_status"] == RecoveryCaseStatus.WAITING_FOR_OUTCOME.value
    assert transport.post_count == 1

    retry = _execute_action(test_client, case_id, run_id)
    assert retry.status_code == 201
    assert transport.post_count == 1
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "post_mode",
    ["reference_mismatch", "amount_mismatch", "currency_mismatch"],
)
def test_provider_response_mismatch_unknown_no_second_post(
    action_seeded_database,
    action_settings,
    post_mode: str,
) -> None:
    transport = MockPaymentLinkTransport(post_mode=post_mode)
    setup = sessionmaker(bind=action_seeded_database, autoflush=False, autocommit=False)()
    case, run_id, _ = setup_recommended_case(setup)
    case_id = case.id
    setup.close()

    app = create_app()
    razorpay = make_mock_client(transport.handler)

    def override_get_db() -> Generator[Session, None, None]:
        session = sessionmaker(bind=action_seeded_database, autoflush=False, autocommit=False)()
        try:
            yield session
        finally:
            session.close()

    def service_override(db: Session = Depends(get_db)) -> RecoveryActionService:
        return RecoveryActionService(db, settings=action_settings, razorpay_client=razorpay)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: action_settings
    app.dependency_overrides[get_recovery_action_service] = service_override
    test_client = TestClient(app, raise_server_exceptions=False)

    first = _execute_action(test_client, case_id, run_id)
    assert first.status_code == 201
    assert first.json()["action"]["status"] == RecoveryActionStatus.UNKNOWN.value
    assert transport.post_count == 1

    retry = _execute_action(test_client, case_id, run_id)
    assert retry.status_code == 201
    assert transport.post_count == 1
    app.dependency_overrides.clear()


def test_stale_approval_version_rejected(action_client, db_session) -> None:
    client, transport = action_client
    case, run_id, _ = setup_recommended_case(db_session, amount_at_risk_minor=2_000_000)
    create = _execute_action(client, case.id, run_id)
    action_id = create.json()["action"]["id"]
    approve = client.post(
        f"/api/v1/recovery-actions/{action_id}/approve",
        headers=ADMIN_HEADERS,
        json={"expected_case_version": 1},
    )
    assert approve.status_code == 409
    assert approve.json()["error"]["code"] == "STALE_CASE_VERSION"
    assert transport.post_count == 0


def test_max_attempts_blocks_action(action_client, db_session) -> None:
    client, transport = action_client
    policy = db_session.execute(
        select(MerchantPolicy).where(MerchantPolicy.organization_id == DEMO_ORGANIZATION_ID)
    ).scalar_one()
    policy.max_recovery_attempts = 1
    db_session.commit()
    case, run_id, _ = setup_recommended_case(db_session)
    existing_action = RecoveryAction(
        organization_id=DEMO_ORGANIZATION_ID,
        case_id=case.id,
        action_type=RecoveryActionType.WAIT.value,
        status=RecoveryActionStatus.SCHEDULED.value,
        attempt_number=1,
        requires_approval=False,
        idempotency_key=f"seed-attempt:{case.id}:1",
    )
    db_session.add(existing_action)
    db_session.commit()
    response = _execute_action(client, case.id, run_id)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ACTION_BLOCKED_BY_POLICY"
    assert transport.post_count == 0


def test_policy_change_requires_approval(action_client, db_session) -> None:
    client, transport = action_client
    case, run_id, recommendation = setup_recommended_case(db_session, amount_at_risk_minor=500000)
    recommendation.requires_approval = False
    db_session.commit()
    policy = db_session.execute(
        select(MerchantPolicy).where(MerchantPolicy.organization_id == DEMO_ORGANIZATION_ID)
    ).scalar_one()
    policy.auto_action_limit_minor = 100000
    db_session.commit()
    response = _execute_action(client, case.id, run_id)
    assert response.status_code == 201
    assert response.json()["case_status"] == RecoveryCaseStatus.AWAITING_APPROVAL.value
    assert transport.post_count == 0


def test_concurrent_approve_one_post(action_seeded_database, action_settings) -> None:
    transport = MockPaymentLinkTransport()
    setup = sessionmaker(bind=action_seeded_database, autoflush=False, autocommit=False)()
    case, run_id, _ = setup_recommended_case(setup, amount_at_risk_minor=2_000_000)
    case_id = case.id
    setup.close()
    action_id_holder: dict[str, str] = {}
    version_holder: dict[str, int] = {}

    app = create_app()
    razorpay = make_mock_client(transport.handler)

    def override_get_db() -> Generator[Session, None, None]:
        session = sessionmaker(bind=action_seeded_database, autoflush=False, autocommit=False)()
        try:
            yield session
        finally:
            session.close()

    def service_override(db: Session = Depends(get_db)) -> RecoveryActionService:
        return RecoveryActionService(db, settings=action_settings, razorpay_client=razorpay)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: action_settings
    app.dependency_overrides[get_recovery_action_service] = service_override
    client = TestClient(app, raise_server_exceptions=False)
    create = _execute_action(client, case_id, run_id)
    action_id_holder["id"] = create.json()["action"]["id"]
    verify = sessionmaker(bind=action_seeded_database, autoflush=False, autocommit=False)()
    version_holder["v"] = verify.execute(
        select(RecoveryCase).where(RecoveryCase.id == case_id)
    ).scalar_one().version
    verify.close()

    results = []

    def approve_worker() -> None:
        worker_app = create_app()
        worker_app.dependency_overrides[get_db] = override_get_db
        worker_app.dependency_overrides[get_settings] = lambda: action_settings
        worker_app.dependency_overrides[get_recovery_action_service] = service_override
        worker_client = TestClient(worker_app, raise_server_exceptions=False)
        response = worker_client.post(
            f"/api/v1/recovery-actions/{action_id_holder['id']}/approve",
            headers=ADMIN_HEADERS,
            json={"expected_case_version": version_holder["v"]},
        )
        results.append(response.status_code)
        worker_app.dependency_overrides.clear()

    threads = [threading.Thread(target=approve_worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    app.dependency_overrides.clear()
    assert 200 in results
    assert 409 in results
    assert transport.post_count == 1
