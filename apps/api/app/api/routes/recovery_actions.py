"""Recovery action routes (Prompt 16)."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.actions.exceptions import (
    ActionBlockedByPolicyError,
    ActionConflictError,
    ActionNotFoundError,
    CaseNotActionableError,
    StaleRecommendationError,
    UnsupportedActionError,
)
from app.actions.service import RecoveryActionService
from app.core.auth import AuthContext, get_current_user
from app.core.config import Settings, get_settings
from app.core.deps import get_db
from app.core.errors import AppError, ConflictError, ForbiddenError, NotFoundError
from app.domain.enums import AuditActorType, UserRole
from app.schemas.recovery_actions import (
    ApproveRecoveryActionRequest,
    ApproveRecoveryActionResponse,
    CreateRecoveryActionRequest,
    CreateRecoveryActionResponse,
    CustomerActionResponse,
    RecoveryActionSummary,
    RejectRecoveryActionRequest,
    RejectRecoveryActionResponse,
)
from app.workflows.exceptions import CaseNotFoundError, StaleVersionError, TerminalStateError

router = APIRouter(tags=["recovery-actions"])

_EXECUTE_ROLES = frozenset({UserRole.OPERATOR, UserRole.ADMIN})
_APPROVAL_ROLES = frozenset({UserRole.ADMIN})


def get_recovery_action_service(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RecoveryActionService:
    return RecoveryActionService(db, settings=settings)


async def require_execute_role(
    current_user: Annotated[AuthContext, Depends(get_current_user)],
) -> AuthContext:
    if current_user.role not in _EXECUTE_ROLES:
        raise ForbiddenError(
            code="ROLE_NOT_ALLOWED",
            message="Action execution requires OPERATOR or ADMIN role.",
        )
    return current_user


async def require_approval_role(
    current_user: Annotated[AuthContext, Depends(get_current_user)],
) -> AuthContext:
    if current_user.role not in _APPROVAL_ROLES:
        raise ForbiddenError(
            code="ROLE_NOT_ALLOWED",
            message="Action approval requires ADMIN role.",
        )
    return current_user


def _action_summary(action: Any) -> RecoveryActionSummary:
    return RecoveryActionSummary(
        id=action.id,
        action_type=action.action_type,
        status=action.status,
        requires_approval=bool(action.requires_approval),
        provider_reference=getattr(action, "provider_reference", None),
        scheduled_for=getattr(action, "scheduled_for", None),
    )


@router.post(
    "/recovery-cases/{case_id}/actions",
    response_model=CreateRecoveryActionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_recovery_action(
    case_id: UUID,
    request: CreateRecoveryActionRequest,
    current_user: Annotated[AuthContext, Depends(require_execute_role)],
    service: Annotated[RecoveryActionService, Depends(get_recovery_action_service)],
) -> CreateRecoveryActionResponse:
    try:
        result = service.create_case_action(
            case_id=case_id,
            organization_id=current_user.organization_id,
            analysis_run_id=request.analysis_run_id,
            action_type=request.action_type,
            actor_type=AuditActorType.USER,
            actor_id=str(current_user.user_id),
        )
    except CaseNotFoundError as exc:
        raise NotFoundError(message=str(exc)) from exc
    except CaseNotActionableError as exc:
        raise ConflictError(
            code="CASE_ALREADY_RESOLVED",
            message=str(exc),
        ) from exc
    except StaleRecommendationError as exc:
        raise AppError(
            code="ACTION_NOT_IN_ANALYSIS",
            message=str(exc),
            status_code=422,
        ) from exc
    except ActionBlockedByPolicyError as exc:
        raise AppError(
            code="ACTION_BLOCKED_BY_POLICY",
            message="Action blocked by policy.",
            status_code=422,
            details={"reasons": list(exc.reasons)},
        ) from exc
    except UnsupportedActionError as exc:
        raise AppError(
            code="ACTION_NOT_EXECUTABLE",
            message=str(exc),
            status_code=422,
        ) from exc
    except ActionConflictError as exc:
        raise ConflictError(
            code="ACTION_ALREADY_EXISTS",
            message=str(exc),
        ) from exc
    except TerminalStateError as exc:
        raise ConflictError(
            code="CASE_ALREADY_RESOLVED",
            message=str(exc),
        ) from exc

    customer_action = None
    if result.customer_action_type and result.customer_action_url:
        customer_action = CustomerActionResponse(
            type=result.customer_action_type,
            url=result.customer_action_url,
        )
    return CreateRecoveryActionResponse(
        action=_action_summary(result.action),
        case_status=result.case_status.value,
        customer_action=customer_action,
    )


@router.post(
    "/recovery-actions/{action_id}/approve",
    response_model=ApproveRecoveryActionResponse,
)
def approve_recovery_action(
    action_id: UUID,
    request: ApproveRecoveryActionRequest,
    current_user: Annotated[AuthContext, Depends(require_approval_role)],
    service: Annotated[RecoveryActionService, Depends(get_recovery_action_service)],
) -> ApproveRecoveryActionResponse:
    try:
        result = service.approve_action(
            action_id=action_id,
            organization_id=current_user.organization_id,
            expected_case_version=request.expected_case_version,
            approver_id=current_user.user_id,
            actor_type=AuditActorType.USER,
        )
    except ActionNotFoundError as exc:
        raise NotFoundError(message=str(exc)) from exc
    except ActionConflictError as exc:
        raise ConflictError(
            code="ACTION_NOT_PENDING_APPROVAL",
            message=str(exc),
        ) from exc
    except StaleVersionError as exc:
        raise ConflictError(
            code="STALE_CASE_VERSION",
            message=str(exc),
        ) from exc
    except CaseNotActionableError as exc:
        raise ConflictError(
            code="CASE_ALREADY_RESOLVED",
            message=str(exc),
        ) from exc
    except CaseNotFoundError as exc:
        raise NotFoundError(message=str(exc)) from exc
    except StaleRecommendationError as exc:
        raise ConflictError(
            code="STALE_CASE_VERSION",
            message=str(exc),
        ) from exc

    return ApproveRecoveryActionResponse(
        action_id=result.action_id,
        action_status=result.action_status.value,
        case_status=result.case_status.value,
    )


@router.post(
    "/recovery-actions/{action_id}/reject",
    response_model=RejectRecoveryActionResponse,
)
def reject_recovery_action(
    action_id: UUID,
    request: RejectRecoveryActionRequest,
    current_user: Annotated[AuthContext, Depends(require_approval_role)],
    service: Annotated[RecoveryActionService, Depends(get_recovery_action_service)],
) -> RejectRecoveryActionResponse:
    try:
        result = service.reject_action(
            action_id=action_id,
            organization_id=current_user.organization_id,
            reason=request.reason,
            reanalyze=request.reanalyze,
            actor_id=str(current_user.user_id),
            actor_type=AuditActorType.USER,
        )
    except ActionNotFoundError as exc:
        raise NotFoundError(message=str(exc)) from exc
    except ActionConflictError as exc:
        raise ConflictError(
            code="ACTION_NOT_PENDING_APPROVAL",
            message=str(exc),
        ) from exc
    except CaseNotFoundError as exc:
        raise NotFoundError(message=str(exc)) from exc
    except CaseNotActionableError as exc:
        raise ConflictError(
            code="CASE_ALREADY_RESOLVED",
            message=str(exc),
        ) from exc

    return RejectRecoveryActionResponse(
        action_id=result.action_id,
        action_status=result.action_status.value,
        case_status=result.case_status.value,
    )
