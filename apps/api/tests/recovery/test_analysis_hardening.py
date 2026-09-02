"""Recovery analysis hardening tests (Prompt 13 acceptance)."""

from __future__ import annotations

import shutil
import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy import func, select

from app.core.config import Settings
from app.demo.constants import DEMO_ORGANIZATION_ID, MAX_RECOVERY_ATTEMPTS
from app.domain.enums import (
    AnalysisReason,
    AuditActorType,
    RecoveryActionStatus,
    RecoveryActionType,
    RecoveryCaseStatus,
)
from app.ml.service import (
    ModelArtifactError,
    RecoveryPropensityModelService,
    load_trusted_model_bundle,
)
from app.models.audit_log import AuditLog
from app.models.recovery_action import RecoveryAction
from app.models.recovery_case import RecoveryCase
from app.models.recovery_recommendation import RecoveryRecommendation
from app.recovery.service import (
    InsufficientCaseDataError,
    ModelUnavailableError,
    RecoveryAnalysisService,
)
from app.workflows.events import RecoveryEvent
from app.workflows.recovery import (
    TERMINAL_REASON_INSUFFICIENT_CASE_DATA,
    TERMINAL_REASON_MODEL_UNAVAILABLE,
    RecoveryAnalysisWorkflowService,
)
from tests.recovery.conftest import CANONICAL_ARTIFACT_PATH


def test_corrupt_artifact_sha_mismatch_rejected(tmp_path) -> None:
    corrupt_path = tmp_path / "corrupt.joblib"
    sidecar_path = tmp_path / "corrupt.metadata.json"
    shutil.copy(CANONICAL_ARTIFACT_PATH, corrupt_path)
    shutil.copy(
        CANONICAL_ARTIFACT_PATH.with_name("recovery_model.metadata.json"),
        sidecar_path,
    )
    payload = bytearray(corrupt_path.read_bytes())
    payload[-1] ^= 0xFF
    corrupt_path.write_bytes(payload)

    settings = Settings(model_bundle_path=corrupt_path)
    with pytest.raises(ModelArtifactError, match="SHA-256 mismatch"):
        load_trusted_model_bundle(settings)


def test_corrupt_artifact_fallback_when_enabled(analyzable_case, db_session) -> None:
    failing_model = MagicMock(spec=RecoveryPropensityModelService)
    failing_model.score_actions.side_effect = ModelArtifactError("SHA-256 mismatch")

    service = RecoveryAnalysisService(db_session, propensity_model=failing_model)
    result = service.compute_analysis(case=analyzable_case)

    assert result.inference.source == "fallback"
    assert "SHA-256 mismatch" in (result.inference.fallback_reason or "")


def test_corrupt_artifact_terminal_failure_when_no_fallback(
    analyzable_case,
    db_session,
) -> None:
    failing_model = MagicMock(spec=RecoveryPropensityModelService)
    failing_model.score_actions.side_effect = ModelArtifactError("SHA-256 mismatch")

    workflow = RecoveryAnalysisWorkflowService(
        db_session,
        analysis_service=RecoveryAnalysisService(
            db_session,
            propensity_model=failing_model,
            allow_model_fallback=False,
        ),
    )
    with pytest.raises(ModelUnavailableError):
        workflow.analyze_recovery_case(
            case_id=analyzable_case.id,
            organization_id=analyzable_case.organization_id,
            reason=AnalysisReason.MANUAL_ANALYSIS,
            actor_type=AuditActorType.USER,
            actor_id="test-user",
        )

    refreshed = db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == analyzable_case.id)
    ).scalar_one()
    assert refreshed.status == RecoveryCaseStatus.FAILED.value


def _latest_failure_audit(db_session, *, case_id: uuid.UUID) -> AuditLog:
    return db_session.execute(
        select(AuditLog)
        .where(
            AuditLog.case_id == case_id,
            AuditLog.organization_id == DEMO_ORGANIZATION_ID,
            AuditLog.event_type == "CASE_FAILED",
        )
        .order_by(AuditLog.created_at.desc())
    ).scalars().first()


def test_insufficient_data_transitions_to_failed(analyzable_case, db_session) -> None:
    failing_service = MagicMock(spec=RecoveryAnalysisService)
    failing_service.compute_analysis.side_effect = InsufficientCaseDataError(
        "Merchant policy not configured."
    )

    workflow = RecoveryAnalysisWorkflowService(db_session, analysis_service=failing_service)
    with pytest.raises(InsufficientCaseDataError):
        workflow.analyze_recovery_case(
            case_id=analyzable_case.id,
            organization_id=analyzable_case.organization_id,
            reason=AnalysisReason.MANUAL_ANALYSIS,
            actor_type=AuditActorType.USER,
            actor_id="test-user",
        )

    case = db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == analyzable_case.id)
    ).scalar_one()
    assert case.status == RecoveryCaseStatus.FAILED.value

    audit = _latest_failure_audit(db_session, case_id=case.id)
    assert audit is not None
    assert audit.evidence["transition_event"] == RecoveryEvent.ANALYSIS_TERMINAL_FAILURE.value
    assert audit.evidence["previous_status"] == RecoveryCaseStatus.ANALYZING.value
    assert audit.evidence["new_status"] == RecoveryCaseStatus.FAILED.value
    assert audit.evidence["reason"] == TERMINAL_REASON_INSUFFICIENT_CASE_DATA
    assert "traceback" not in audit.evidence
    assert "password" not in str(audit.evidence).lower()

    recommendation_count = db_session.execute(
        select(func.count()).select_from(RecoveryRecommendation).where(
            RecoveryRecommendation.case_id == case.id
        )
    ).scalar_one()
    assert recommendation_count == 0


def test_model_unavailable_transitions_to_failed(analyzable_case, db_session) -> None:
    failing_service = MagicMock(spec=RecoveryAnalysisService)
    failing_service.compute_analysis.side_effect = ModelUnavailableError("inference failed")

    workflow = RecoveryAnalysisWorkflowService(db_session, analysis_service=failing_service)
    with pytest.raises(ModelUnavailableError):
        workflow.analyze_recovery_case(
            case_id=analyzable_case.id,
            organization_id=analyzable_case.organization_id,
            reason=AnalysisReason.MANUAL_ANALYSIS,
            actor_type=AuditActorType.USER,
            actor_id="test-user",
        )

    case = db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == analyzable_case.id)
    ).scalar_one()
    assert case.status == RecoveryCaseStatus.FAILED.value

    audit = _latest_failure_audit(db_session, case_id=case.id)
    assert audit is not None
    assert audit.evidence["reason"] == TERMINAL_REASON_MODEL_UNAVAILABLE


def test_stop_selected_when_interventions_exhausted(analyzable_case, db_session) -> None:
    case = analyzable_case
    for attempt in range(1, MAX_RECOVERY_ATTEMPTS + 1):
        db_session.add(
            RecoveryAction(
                organization_id=case.organization_id,
                case_id=case.id,
                action_type=RecoveryActionType.WAIT.value,
                status=RecoveryActionStatus.SUCCEEDED.value,
                attempt_number=attempt,
                requires_approval=False,
                idempotency_key=f"stop-test:{case.id}:{attempt}",
            )
        )
    db_session.commit()

    result = RecoveryAnalysisService(db_session).compute_analysis(case=case)
    assert result.selected is not None
    assert result.selected.action_type == RecoveryActionType.STOP
    assert result.selected.success_probability == 0
    assert result.selected.expected_value_minor == 0
    assert result.selected.expected_recovered_minor == 0

    stop_row = next(
        row
        for row in result.recommendation_rows
        if row.action_type == RecoveryActionType.STOP.value
    )
    assert stop_row.rank >= 1


def test_fallback_completes_to_recommended(analyzable_case, db_session) -> None:
    failing_model = MagicMock(spec=RecoveryPropensityModelService)
    failing_model.score_actions.side_effect = ModelArtifactError("inference failed")

    workflow = RecoveryAnalysisWorkflowService(
        db_session,
        analysis_service=RecoveryAnalysisService(
            db_session,
            propensity_model=failing_model,
            allow_model_fallback=True,
        ),
    )
    result = workflow.analyze_recovery_case(
        case_id=analyzable_case.id,
        organization_id=analyzable_case.organization_id,
        reason=AnalysisReason.MANUAL_ANALYSIS,
        actor_type=AuditActorType.USER,
        actor_id="test-user",
    )

    assert result.status == RecoveryCaseStatus.RECOMMENDED
    assert result.computation.inference.source == "fallback"

    case = db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == analyzable_case.id)
    ).scalar_one()
    assert case.status == RecoveryCaseStatus.RECOMMENDED.value
    assert case.current_analysis_run_id == result.analysis_run_id
