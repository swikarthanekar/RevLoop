"""Recovery case read routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import AuthContext, get_current_user
from app.core.deps import get_db
from app.repositories.recovery_case_repo import RecoveryCaseListFilters
from app.schemas.common import RecoveryCaseSort
from app.schemas.recovery_case import RecoveryCaseDetailResponse, RecoveryCaseListResponse
from app.schemas.timeline import TimelineResponse
from app.services.recovery_case_service import RecoveryCaseService
from app.services.timeline_service import TimelineService

router = APIRouter(prefix="/recovery-cases", tags=["recovery-cases"])


def _parse_status_filter(status: list[str] | None) -> list[str] | None:
    if not status:
        return None
    values: list[str] = []
    for entry in status:
        values.extend(part.strip() for part in entry.split(",") if part.strip())
    return values or None


@router.get("", response_model=RecoveryCaseListResponse)
def list_recovery_cases(
    current_user: Annotated[AuthContext, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    status: Annotated[list[str] | None, Query()] = None,
    case_type: Annotated[str | None, Query()] = None,
    failure_category: Annotated[str | None, Query()] = None,
    min_amount_minor: Annotated[int | None, Query(ge=0)] = None,
    max_amount_minor: Annotated[int | None, Query(ge=0)] = None,
    min_confidence: Annotated[float | None, Query(ge=0.0, le=1.0)] = None,
    customer_id: Annotated[UUID | None, Query()] = None,
    search: Annotated[str | None, Query(min_length=1)] = None,
    sort: Annotated[RecoveryCaseSort, Query()] = RecoveryCaseSort.PRIORITY_DESC,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RecoveryCaseListResponse:
    if (
        min_amount_minor is not None
        and max_amount_minor is not None
        and max_amount_minor < min_amount_minor
    ):
        from fastapi import HTTPException

        raise HTTPException(
            status_code=422,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "max_amount_minor must be greater than or equal to min_amount_minor.",
            },
        )

    filters = RecoveryCaseListFilters(
        statuses=_parse_status_filter(status),
        case_type=case_type,
        failure_category=failure_category,
        min_amount_minor=min_amount_minor,
        max_amount_minor=max_amount_minor,
        min_confidence=min_confidence,
        customer_id=customer_id,
        search=search,
    )
    service = RecoveryCaseService(db)
    return service.list_cases(
        current_user.organization_id,
        filters=filters,
        sort=sort,
        limit=limit,
        offset=offset,
    )


@router.get("/{case_id}", response_model=RecoveryCaseDetailResponse)
def get_recovery_case(
    case_id: UUID,
    current_user: Annotated[AuthContext, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> RecoveryCaseDetailResponse:
    service = RecoveryCaseService(db)
    return service.get_case_detail(current_user.organization_id, case_id)


@router.get("/{case_id}/timeline", response_model=TimelineResponse)
def get_recovery_case_timeline(
    case_id: UUID,
    current_user: Annotated[AuthContext, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> TimelineResponse:
    service = TimelineService(db)
    return service.get_case_timeline(current_user.organization_id, case_id)
