"""Recovery case analysis routes."""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.ai.explanations import RecommendationExplanationService
from app.core.auth import AuthContext, get_current_user
from app.core.config import Settings, get_settings
from app.core.deps import get_db
from app.core.errors import AppError, ForbiddenError, NotFoundError
from app.domain.capabilities import advisory_reason_text
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
    RecommendationExplanationResponse,
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

logger = logging.getLogger(__name__)

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
            execution_mode=candidate.execution_mode,
            advisory_reason_code=candidate.advisory_reason_code,
            advisory_reason=advisory_reason_text(candidate.action_type),
        )
        for candidate in candidates
    ]


_EXPLANATION_SERVICE_FACTORY = RecommendationExplanationService


def _build_explanation_service(settings: Settings) -> RecommendationExplanationService:
    return _EXPLANATION_SERVICE_FACTORY(settings=settings)


@router.post("/{case_id}/analyze", response_model=AnalyzeRecoveryCaseResponse)
def analyze_recovery_case(
    case_id: UUID,
    request: AnalyzeRecoveryCaseRequest,
    current_user: Annotated[AuthContext, Depends(require_analysis_role)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AnalyzeRecoveryCaseResponse:
    workflow = RecoveryAnalysisWorkflowService(db, settings=settings)
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

    explanation_payload = None
    explanation_source = None
    if result.computation.selected is not None:
        explanation_service = _build_explanation_service(settings)
        try:
            explanation_result = explanation_service.enrich(
                db,
                case_id=case_id,
                organization_id=current_user.organization_id,
                analysis_run_id=result.analysis_run_id,
            )
        except Exception:  # noqa: BLE001 - see below
            # `analyze_recovery_case` above has already COMMITTED the analysis:
            # the case has transitioned, the recommendations are durable, and
            # the audit trail is written. Enrichment is presentation only and
            # runs afterwards, so letting it raise here turned a fully
            # successful, committed analysis into `500 INTERNAL_ERROR` -- the
            # caller saw a failure for work that had actually succeeded, and
            # would reasonably retry a non-idempotent operation.
            #
            # `enrich` already degrades LLM failures to a template internally;
            # what escapes it is narrower and less predictable (a `ValueError`
            # from the analysis-run currency check, `NoResultFound` from a
            # concurrent re-analysis, a validation error). Catching broadly is
            # deliberate: nothing this component can raise is worth discarding
            # a committed analysis over. The response simply carries no
            # explanation, which every client already handles -- both fields
            # are optional and are absent whenever no action was selected.
            logger.warning(
                "Explanation enrichment failed after a committed analysis "
                "(case=%s run=%s); returning the analysis without an "
                "explanation.",
                case_id,
                result.analysis_run_id,
                exc_info=True,
            )
        else:
            explanation_payload = RecommendationExplanationResponse(
                summary=explanation_result.explanation.summary,
                evidence=list(explanation_result.explanation.evidence),
                safety=list(explanation_result.explanation.safety),
                customer_impact=explanation_result.explanation.customer_impact,
            )
            explanation_source = explanation_result.explanation_source

    ranked = result.computation.ranked_candidates
    return AnalyzeRecoveryCaseResponse(
        case_id=result.case_id,
        analysis_run_id=result.analysis_run_id,
        status=result.status,
        selected=_selected_response(result.computation.selected),
        top_ranked_action=ranked[0].action_type.value if ranked else None,
        candidates=_candidate_responses(ranked),
        explanation=explanation_payload,
        explanation_source=explanation_source,
    )
