"""Recovery analysis API tests."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Generator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.auth import AuthContext, get_current_user
from app.core.config import get_settings
from app.core.deps import get_db
from app.demo.constants import (
    DEMO_AUTH_USER_ANALYST_ID,
    DEMO_CASE_UPI_DOWNTIME_ID,
    DEMO_ORGANIZATION_ID,
)
from app.domain.enums import AuditActorType, RecoveryCaseStatus, UserRole
from app.main import create_app
from app.models.audit_log import AuditLog
from app.models.recovery_recommendation import RecoveryRecommendation
from app.workflows.events import RecoveryEvent
from app.workflows.schemas import TransitionContext
from app.workflows.state_machine import RecoveryCaseStateMachine
from tests.api.conftest import DEMO_AUTH_HEADERS
from tests.recovery.conftest import CANONICAL_ARTIFACT_SHA256
from tests.recovery.helpers import load_case_fresh

pytestmark = pytest.mark.usefixtures("seeded_database")


def test_analyze_detected_case_success(api_client, analyzable_case) -> None:
    case_id = analyzable_case.id
    response = api_client.post(
        f"/api/v1/recovery-cases/{case_id}/analyze",
        headers=DEMO_AUTH_HEADERS,
        json={"reason": "MANUAL_ANALYSIS"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["case_id"] == str(case_id)
    assert payload["status"] == RecoveryCaseStatus.RECOMMENDED.value
    assert payload["analysis_run_id"]
    assert payload["selected"]["action_type"]
    assert payload["candidates"]
    assert all(candidate["rank"] >= 1 for candidate in payload["candidates"])


def test_analyze_persists_candidates_and_selected(
    api_client,
    analyzable_case,
    fresh_db_session,
) -> None:
    case_id = analyzable_case.id
    response = api_client.post(
        f"/api/v1/recovery-cases/{case_id}/analyze",
        headers=DEMO_AUTH_HEADERS,
        json={"reason": "MANUAL_ANALYSIS"},
    )
    assert response.status_code == 200
    payload = response.json()
    run_id = uuid.UUID(payload["analysis_run_id"])

    rows = fresh_db_session.execute(
        select(RecoveryRecommendation).where(
            RecoveryRecommendation.case_id == case_id,
            RecoveryRecommendation.analysis_run_id == run_id,
        )
    ).scalars().all()
    assert len(rows) == len(payload["candidates"])
    rank1 = next(row for row in rows if row.rank == 1)
    assert rank1.action_type == payload["selected"]["action_type"]
    assert float(rank1.success_probability) == pytest.approx(
        payload["selected"]["success_probability"], rel=1e-6
    )


def test_reanalysis_preserves_previous_run(
    api_client,
    analyzable_case,
    session_factory,
    fresh_db_session,
) -> None:
    case_id = analyzable_case.id
    first = api_client.post(
        f"/api/v1/recovery-cases/{case_id}/analyze",
        headers=DEMO_AUTH_HEADERS,
        json={"reason": "MANUAL_ANALYSIS"},
    )
    assert first.status_code == 200
    first_run_id = uuid.UUID(first.json()["analysis_run_id"])

    first_rows = fresh_db_session.execute(
        select(RecoveryRecommendation).where(
            RecoveryRecommendation.analysis_run_id == first_run_id
        )
    ).scalars().all()
    first_snapshot = {
        (row.action_type, row.rank, row.expected_value_minor, row.success_probability)
        for row in first_rows
    }

    case = load_case_fresh(
        session_factory,
        case_id=case_id,
        organization_id=DEMO_ORGANIZATION_ID,
    )
    assert case.status == RecoveryCaseStatus.RECOMMENDED.value

    schedule_session = session_factory()
    try:
        state_machine = RecoveryCaseStateMachine()
        schedule_context = TransitionContext(
            organization_id=case.organization_id,
            actor_type=AuditActorType.USER,
            actor_id="test-scheduler",
            action_id=uuid.uuid4(),
            scheduled_for=datetime.now(timezone.utc),
        )
        state_machine.transition_case(
            schedule_session,
            case_id=case_id,
            organization_id=case.organization_id,
            expected_version=case.version,
            event=RecoveryEvent.ACTION_SCHEDULED,
            context=schedule_context,
        )
    finally:
        schedule_session.close()

    second = api_client.post(
        f"/api/v1/recovery-cases/{case_id}/analyze",
        headers=DEMO_AUTH_HEADERS,
        json={"reason": "SCHEDULED_REEVALUATION"},
    )
    assert second.status_code == 200
    second_run_id = uuid.UUID(second.json()["analysis_run_id"])
    assert second_run_id != first_run_id

    preserved = fresh_db_session.execute(
        select(RecoveryRecommendation).where(
            RecoveryRecommendation.analysis_run_id == first_run_id
        )
    ).scalars().all()
    assert {
        (row.action_type, row.rank, row.expected_value_minor, row.success_probability)
        for row in preserved
    } == first_snapshot

    final_case = load_case_fresh(
        session_factory,
        case_id=case_id,
        organization_id=DEMO_ORGANIZATION_ID,
    )
    assert final_case.current_analysis_run_id == second_run_id
    assert final_case.status == RecoveryCaseStatus.RECOMMENDED.value


def test_invalid_state_returns_409(api_client) -> None:
    response = api_client.post(
        f"/api/v1/recovery-cases/{DEMO_CASE_UPI_DOWNTIME_ID}/analyze",
        headers=DEMO_AUTH_HEADERS,
        json={"reason": "MANUAL_ANALYSIS"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_CASE_STATE"


def test_unauthorized_returns_401(api_client, analyzable_case) -> None:
    response = api_client.post(
        f"/api/v1/recovery-cases/{analyzable_case.id}/analyze",
        json={"reason": "MANUAL_ANALYSIS"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_forbidden_role_returns_403(
    seeded_database,
    api_demo_settings,
    analyzable_case,
    monkeypatch,
) -> None:
    import app.api.routes.recovery_analysis as recovery_analysis_routes

    monkeypatch.setattr(recovery_analysis_routes, "_ANALYZE_ROLES", frozenset({UserRole.ADMIN}))

    app = create_app()

    def override_get_db() -> Generator[Session, None, None]:
        session = sessionmaker(bind=seeded_database, autoflush=False, autocommit=False)()
        try:
            yield session
        finally:
            session.close()

    async def override_get_current_user() -> AuthContext:
        return AuthContext(
            user_id=DEMO_AUTH_USER_ANALYST_ID,
            organization_id=DEMO_ORGANIZATION_ID,
            role=UserRole.ANALYST,
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: api_demo_settings
    app.dependency_overrides[get_current_user] = override_get_current_user

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        f"/api/v1/recovery-cases/{analyzable_case.id}/analyze",
        headers=DEMO_AUTH_HEADERS,
        json={"reason": "MANUAL_ANALYSIS"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ROLE_NOT_ALLOWED"


def test_tenant_isolation_returns_404(other_org_client, analyzable_case) -> None:
    response = other_org_client.post(
        f"/api/v1/recovery-cases/{analyzable_case.id}/analyze",
        headers=DEMO_AUTH_HEADERS,
        json={"reason": "MANUAL_ANALYSIS"},
    )
    assert response.status_code == 404


def test_model_metadata_and_artifact_hash_persisted(
    api_client,
    analyzable_case,
    fresh_db_session,
) -> None:
    response = api_client.post(
        f"/api/v1/recovery-cases/{analyzable_case.id}/analyze",
        headers=DEMO_AUTH_HEADERS,
        json={"reason": "MANUAL_ANALYSIS"},
    )
    assert response.status_code == 200
    run_id = uuid.UUID(response.json()["analysis_run_id"])
    row = fresh_db_session.execute(
        select(RecoveryRecommendation).where(
            RecoveryRecommendation.analysis_run_id == run_id,
            RecoveryRecommendation.rank == 1,
        )
    ).scalar_one()
    assert row.model_version
    assert row.feature_schema_version == "recovery_features_v1"
    metadata = next(factor for factor in row.factors if factor["code"] == "MODEL_METADATA")
    assert metadata["artifact_sha256"] == CANONICAL_ARTIFACT_SHA256
    assert metadata["model_family"] == "logistic_regression"


def test_concurrent_analyze_requests_one_wins(
    seeded_database,
    api_demo_settings,
    session_factory,
    fresh_db_session,
) -> None:
    setup_session = session_factory()
    try:
        from tests.workflows.helpers import create_case, create_customer

        customer = create_customer(setup_session, organization_id=DEMO_ORGANIZATION_ID)
        case = create_case(
            setup_session,
            organization_id=DEMO_ORGANIZATION_ID,
            customer_id=customer.id,
            status=RecoveryCaseStatus.DETECTED,
        )
        setup_session.commit()
        case_id = case.id
        initial_version = case.version
    finally:
        setup_session.close()

    results: list[tuple[int, dict | None]] = []
    barrier = threading.Barrier(2)

    def worker() -> None:
        app = create_app()

        def override_get_db() -> Generator[Session, None, None]:
            session = sessionmaker(bind=seeded_database, autoflush=False, autocommit=False)()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_settings] = lambda: api_demo_settings
        client = TestClient(app, raise_server_exceptions=False)
        barrier.wait(timeout=5)
        response = client.post(
            f"/api/v1/recovery-cases/{case_id}/analyze",
            headers=DEMO_AUTH_HEADERS,
            json={"reason": "MANUAL_ANALYSIS"},
        )
        body = response.json() if response.content else None
        results.append((response.status_code, body))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert len(results) == 2
    status_codes = sorted(code for code, _ in results)
    assert status_codes == [200, 409]

    success_bodies = [body for code, body in results if code == 200]
    assert len(success_bodies) == 1
    assert success_bodies[0]["status"] == RecoveryCaseStatus.RECOMMENDED.value

    final_case = load_case_fresh(
        session_factory,
        case_id=case_id,
        organization_id=DEMO_ORGANIZATION_ID,
    )
    assert final_case.status == RecoveryCaseStatus.RECOMMENDED.value
    assert final_case.version == initial_version + 2
    assert final_case.current_analysis_run_id is not None

    run_count = fresh_db_session.execute(
        select(func.count(func.distinct(RecoveryRecommendation.analysis_run_id))).where(
            RecoveryRecommendation.case_id == case_id
        )
    ).scalar_one()
    assert run_count == 1

    recommendation_count = fresh_db_session.execute(
        select(func.count()).select_from(RecoveryRecommendation).where(
            RecoveryRecommendation.case_id == case_id
        )
    ).scalar_one()
    assert recommendation_count > 0


def test_insufficient_data_api_returns_422_and_failed(
    seeded_database,
    api_demo_settings,
    session_factory,
    fresh_db_session,
    monkeypatch,
) -> None:
    from app.recovery.service import InsufficientCaseDataError, RecoveryAnalysisService
    from app.workflows import recovery as recovery_workflow_module

    original_service = RecoveryAnalysisService

    class FailingService(RecoveryAnalysisService):
        def compute_analysis(self, **kwargs):
            raise InsufficientCaseDataError("Merchant policy not configured.")

    monkeypatch.setattr(recovery_workflow_module, "RecoveryAnalysisService", FailingService)

    setup_session = session_factory()
    try:
        from tests.workflows.helpers import create_case, create_customer

        customer = create_customer(setup_session, organization_id=DEMO_ORGANIZATION_ID)
        case = create_case(
            setup_session,
            organization_id=DEMO_ORGANIZATION_ID,
            customer_id=customer.id,
            status=RecoveryCaseStatus.DETECTED,
        )
        setup_session.commit()
        case_id = case.id
    finally:
        setup_session.close()

    app = create_app()

    def override_get_db() -> Generator[Session, None, None]:
        session = sessionmaker(bind=seeded_database, autoflush=False, autocommit=False)()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: api_demo_settings
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        f"/api/v1/recovery-cases/{case_id}/analyze",
        headers=DEMO_AUTH_HEADERS,
        json={"reason": "MANUAL_ANALYSIS"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INSUFFICIENT_CASE_DATA"

    final_case = load_case_fresh(
        session_factory,
        case_id=case_id,
        organization_id=DEMO_ORGANIZATION_ID,
    )
    assert final_case.status == RecoveryCaseStatus.FAILED.value

    audit = fresh_db_session.execute(
        select(AuditLog)
        .where(
            AuditLog.case_id == case_id,
            AuditLog.event_type == "CASE_FAILED",
        )
        .order_by(AuditLog.created_at.desc())
    ).scalars().first()
    assert audit is not None
    assert audit.evidence["reason"] == "INSUFFICIENT_CASE_DATA"

    monkeypatch.setattr(recovery_workflow_module, "RecoveryAnalysisService", original_service)


def test_model_unavailable_api_returns_503_and_failed(
    seeded_database,
    api_demo_settings,
    session_factory,
    fresh_db_session,
    monkeypatch,
) -> None:
    from app.recovery.service import ModelUnavailableError, RecoveryAnalysisService
    from app.workflows import recovery as recovery_workflow_module

    class FailingService(RecoveryAnalysisService):
        def compute_analysis(self, **kwargs):
            raise ModelUnavailableError("inference failed")

    monkeypatch.setattr(recovery_workflow_module, "RecoveryAnalysisService", FailingService)

    setup_session = session_factory()
    try:
        from tests.workflows.helpers import create_case, create_customer

        customer = create_customer(setup_session, organization_id=DEMO_ORGANIZATION_ID)
        case = create_case(
            setup_session,
            organization_id=DEMO_ORGANIZATION_ID,
            customer_id=customer.id,
            status=RecoveryCaseStatus.DETECTED,
        )
        setup_session.commit()
        case_id = case.id
    finally:
        setup_session.close()

    app = create_app()

    def override_get_db() -> Generator[Session, None, None]:
        session = sessionmaker(bind=seeded_database, autoflush=False, autocommit=False)()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: api_demo_settings
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        f"/api/v1/recovery-cases/{case_id}/analyze",
        headers=DEMO_AUTH_HEADERS,
        json={"reason": "MANUAL_ANALYSIS"},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "MODEL_UNAVAILABLE_AND_NO_FALLBACK"

    final_case = load_case_fresh(
        session_factory,
        case_id=case_id,
        organization_id=DEMO_ORGANIZATION_ID,
    )
    assert final_case.status == RecoveryCaseStatus.FAILED.value
