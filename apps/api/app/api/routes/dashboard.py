"""Dashboard read routes."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import AuthContext, get_current_user
from app.core.deps import get_db
from app.schemas.common import DashboardSourceFilter
from app.schemas.dashboard import DashboardSummaryResponse
from app.services.analytics import AnalyticsService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary(
    current_user: Annotated[AuthContext, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    from_dt: Annotated[datetime | None, Query(alias="from")] = None,
    to_dt: Annotated[datetime | None, Query(alias="to")] = None,
    source: Annotated[DashboardSourceFilter, Query()] = DashboardSourceFilter.ALL,
) -> DashboardSummaryResponse:
    if from_dt is not None and to_dt is not None and to_dt < from_dt:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=422,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "Query parameter 'to' must be greater than or equal to 'from'.",
            },
        )

    service = AnalyticsService(db)
    return service.get_dashboard_summary(
        current_user.organization_id,
        from_dt=from_dt,
        to_dt=to_dt,
        source=source,
    )
