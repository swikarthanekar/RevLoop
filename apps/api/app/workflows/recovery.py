"""Workflow orchestration for recovery case analysis (Prompt 13)."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.domain.enums import AnalysisReason, AuditActorType, RecoveryCaseStatus
from app.recovery.service import (
    AnalysisComputationResult,
    InsufficientCaseDataError,
    InvalidCaseStateForAnalysisError,
    ModelUnavailableError,
    RecoveryAnalysisService,
    map_analysis_reason_to_event,
)
from app.repositories.recovery_cases import RecoveryCaseWorkflowRepository
from app.workflows.events import RecoveryEvent
from app.workflows.exceptions import (
    CaseNotFoundError,
    InvalidTransitionError,
    StaleVersionError,
    TerminalStateError,
    WorkflowError,
)
from app.workflows.schemas import TransitionContext
from app.workflows.state_machine import RecoveryCaseStateMachine

logger = logging.getLogger(__name__)

TERMINAL_REASON_INSUFFICIENT_CASE_DATA = "INSUFFICIENT_CASE_DATA"
TERMINAL_REASON_MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE_AND_NO_FALLBACK"


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _build_entry_context(
    *,
    organization_id: UUID,
    actor_type: AuditActorType,
    actor_id: str | None,
    reason: AnalysisReason,
    entry_event: RecoveryEvent,
) -> TransitionContext:
    return TransitionContext(
        organization_id=organization_id,
        actor_type=actor_type,
        actor_id=actor_id,
        reason=reason.value,
        scheduled_for=_utcnow() if entry_event == RecoveryEvent.REEVALUATION_DUE else None,
    )


@dataclass(frozen=True)
class AnalyzeCaseWorkflowResult:
    case_id: UUID
    analysis_run_id: UUID
    status: RecoveryCaseStatus
    computation: AnalysisComputationResult


def finalize_terminal_analysis_failure(
    session: Session,
    *,
    case_id: UUID,
    organization_id: UUID,
    reason: str,
    actor_type: AuditActorType,
    actor_id: str | None,
    state_machine: RecoveryCaseStateMachine,
    case_repo: RecoveryCaseWorkflowRepository,
) -> bool:
    """Transition ANALYZING -> FAILED when analysis cannot complete safely.

    Returns True when ANALYSIS_TERMINAL_FAILURE was applied.
    Returns False when the case is no longer ANALYZING or a race won.
    """
    case = case_repo.get_case(
        session,
        case_id=case_id,
        organization_id=organization_id,
    )
    if case is None:
        return False
    if RecoveryCaseStatus(case.status) != RecoveryCaseStatus.ANALYZING:
        return False

    context = TransitionContext(
        organization_id=organization_id,
        actor_type=actor_type,
        actor_id=actor_id,
        reason=reason,
    )
    try:
        state_machine.transition_case(
            session,
            case_id=case_id,
            organization_id=organization_id,
            expected_version=case.version,
            event=RecoveryEvent.ANALYSIS_TERMINAL_FAILURE,
            context=context,
        )
        return True
    except (StaleVersionError, InvalidTransitionError, TerminalStateError) as exc:
        logger.info(
            "Skipped ANALYSIS_TERMINAL_FAILURE for case %s after analysis error: %s",
            case_id,
            exc,
        )
        return False
    except WorkflowError as exc:
        logger.warning(
            "Workflow error during ANALYSIS_TERMINAL_FAILURE for case %s: %s",
            case_id,
            exc,
        )
        return False


class RecoveryAnalysisWorkflowService:
    """Coordinates state-machine transitions and recovery analysis persistence."""

    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        state_machine: RecoveryCaseStateMachine | None = None,
        analysis_service: RecoveryAnalysisService | None = None,
        case_repo: RecoveryCaseWorkflowRepository | None = None,
    ) -> None:
        self._session = session
        self._state_machine = state_machine or RecoveryCaseStateMachine()
        runtime_settings = settings or get_settings()
        self._analysis_service = analysis_service or RecoveryAnalysisService(
            session,
            settings=runtime_settings,
        )
        self._case_repo = case_repo or RecoveryCaseWorkflowRepository()

    def analyze_recovery_case(
        self,
        *,
        case_id: UUID,
        organization_id: UUID,
        reason: AnalysisReason,
        actor_type: AuditActorType,
        actor_id: str | None,
    ) -> AnalyzeCaseWorkflowResult:
        case = self._case_repo.get_case(
            self._session,
            case_id=case_id,
            organization_id=organization_id,
        )
        if case is None:
            raise CaseNotFoundError(case_id=case_id, organization_id=organization_id)

        current_status = RecoveryCaseStatus(case.status)
        entry_event = map_analysis_reason_to_event(status=current_status, reason=reason)
        if entry_event is None:
            raise InvalidCaseStateForAnalysisError(
                f"Analysis reason {reason.value} is not allowed from status {current_status.value}."
            )

        entry_context = _build_entry_context(
            organization_id=organization_id,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
            entry_event=entry_event,
        )
        self._state_machine.transition_case(
            self._session,
            case_id=case_id,
            organization_id=organization_id,
            expected_version=case.version,
            event=entry_event,
            context=entry_context,
        )

        case = self._require_case(case_id=case_id, organization_id=organization_id)
        analysis_run_id = uuid.uuid4()
        try:
            computation = self._analysis_service.compute_analysis(
                case=case,
                analysis_run_id=analysis_run_id,
            )
            self._analysis_service.persist_analysis(case=case, result=computation)
        except InsufficientCaseDataError:
            self._session.rollback()
            finalize_terminal_analysis_failure(
                self._session,
                case_id=case_id,
                organization_id=organization_id,
                reason=TERMINAL_REASON_INSUFFICIENT_CASE_DATA,
                actor_type=actor_type,
                actor_id=actor_id,
                state_machine=self._state_machine,
                case_repo=self._case_repo,
            )
            raise
        except ModelUnavailableError:
            self._session.rollback()
            finalize_terminal_analysis_failure(
                self._session,
                case_id=case_id,
                organization_id=organization_id,
                reason=TERMINAL_REASON_MODEL_UNAVAILABLE,
                actor_type=actor_type,
                actor_id=actor_id,
                state_machine=self._state_machine,
                case_repo=self._case_repo,
            )
            raise
        except Exception:
            self._session.rollback()
            raise

        case = self._require_case(case_id=case_id, organization_id=organization_id)
        completion_metadata = {
            "model_version": computation.inference.model_version,
            "model_family": computation.inference.model_family,
            "feature_schema_version": computation.inference.feature_schema_version,
            "artifact_sha256": computation.inference.artifact_sha256,
            "inference_source": computation.inference.source,
        }
        if computation.inference.fallback_reason:
            completion_metadata["fallback_reason"] = computation.inference.fallback_reason

        completion_context = TransitionContext(
            organization_id=organization_id,
            actor_type=actor_type,
            actor_id=actor_id,
            analysis_run_id=analysis_run_id,
            reason=reason.value,
            metadata=completion_metadata,
        )
        completion = self._state_machine.transition_case(
            self._session,
            case_id=case_id,
            organization_id=organization_id,
            expected_version=case.version,
            event=RecoveryEvent.ANALYSIS_COMPLETED,
            context=completion_context,
        )

        return AnalyzeCaseWorkflowResult(
            case_id=case_id,
            analysis_run_id=analysis_run_id,
            status=completion.new_status,
            computation=computation,
        )

    def _require_case(self, *, case_id: UUID, organization_id: UUID):
        case = self._case_repo.get_case(
            self._session,
            case_id=case_id,
            organization_id=organization_id,
        )
        if case is None:
            raise CaseNotFoundError(case_id=case_id, organization_id=organization_id)
        return case
