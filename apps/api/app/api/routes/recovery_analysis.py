"""Recovery case analysis routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import AuthContext, get_current_user
from app.core.deps import get_db
from app.core.errors import AppError, ForbiddenError, NotFoundError
from app.domain.enums import AuditActorType, UserRole
from app.recovery.service import (
    InsufficientCaseDataError,
    InvalidCaseStateForAnalysisError,
    ModelUnavailableError,
)
from app.schemas.recovery_analysis import (
    AnalyzeRecoveryCaseRequest,
    AnalyzeRecoveryCaseResponse,
    CandidateRecommendationResponse,
    SelectedRecommendationResponse,
)
from app.workflows.exceptions import (
    CaseNotFoundError,
    InvalidTransitionError,
    StaleVersionError,
    TerminalStateError,
    WorkflowError,
)
from app.workflows.recovery import RecoveryAnalysisWorkflowService

router = APIRouter(prefix="/recovery-cases", tags=["recovery-analysis"])

_ANALYZE_ROLES = frozenset({UserRole.ANALYST, UserRole.OPERATOR, UserRole.ADMIN})


async def require_analysis_role(
    current_user: Annotated[AuthContext, Depends(get_current_user)],
) -> AuthContext:
    if current_user.role not in _ANALYZE_ROLES:
        raise ForbiddenError(
            code="ROLE_NOT_ALLOWED",
            message="Analysis requires ANALYST, OPERATOR, or ADMIN role.",
        )
    return current_user


def _selected_response(
    selected,
) -> SelectedRecommendationResponse | None:
    if selected is None:
        return None
    return SelectedRecommendationResponse(
        action_type=selected.action_type.value,
        success_probability=float(selected.success_probability),
        expected_recovered_minor=selected.expected_recovered_minor,
        expected_value_minor=selected.expected_value_minor,
        confidence=float(selected.confidence),
        requires_approval=selected.requires_approval,
    )


def _candidate_responses(candidates) -> list[CandidateRecommendationResponse]:
    return [
        CandidateRecommendationResponse(
            action_type=candidate.action_type.value,
            rank=candidate.rank,
            success_probability=float(candidate.success_probability),
            expected_recovered_minor=candidate.expected_recovered_minor,
            expected_value_minor=candidate.expected_value_minor,
            confidence=float(candidate.confidence),
            requires_approval=candidate.requires_approval,
            policy_eligible=candidate.eligible,
        )
        for candidate in candidates
    ]


@router.post("/{case_id}/analyze", response_model=AnalyzeRecoveryCaseResponse)
def analyze_recovery_case(
    case_id: UUID,
    request: AnalyzeRecoveryCaseRequest,
    current_user: Annotated[AuthContext, Depends(require_analysis_role)],
    db: Annotated[Session, Depends(get_db)],
) -> AnalyzeRecoveryCaseResponse:
    workflow = RecoveryAnalysisWorkflowService(db)
    try:
        result = workflow.analyze_recovery_case(
            case_id=case_id,
            organization_id=current_user.organization_id,
            reason=request.reason,
            actor_type=AuditActorType.USER,
            actor_id=str(current_user.user_id),
        )
    except CaseNotFoundError as exc:
        raise NotFoundError(message=str(exc)) from exc
    except InvalidCaseStateForAnalysisError as exc:
        raise AppError(
            code="INVALID_CASE_STATE",
            message=str(exc),
            status_code=409,
        ) from exc
    except (InvalidTransitionError, TerminalStateError, StaleVersionError) as exc:
        raise AppError(
            code="INVALID_CASE_STATE",
            message=str(exc),
            status_code=409,
        ) from exc
    except InsufficientCaseDataError as exc:
        raise AppError(
            code="INSUFFICIENT_CASE_DATA",
            message=str(exc),
            status_code=422,
        ) from exc
    except ModelUnavailableError as exc:
        raise AppError(
            code="MODEL_UNAVAILABLE_AND_NO_FALLBACK",
            message=str(exc),
            status_code=503,
        ) from exc
    except WorkflowError as exc:
        raise AppError(
            code="WORKFLOW_ERROR",
            message=str(exc),
            status_code=409,
        ) from exc

    return AnalyzeRecoveryCaseResponse(
        case_id=result.case_id,
        analysis_run_id=result.analysis_run_id,
        status=result.status,
        selected=_selected_response(result.computation.selected),
        candidates=_candidate_responses(result.computation.ranked_candidates),
    )
