"""Read-only view of received provider webhooks.

Strictly a read. There is deliberately no replay endpoint: re-firing a webhook
during a live demo is a write path that can disturb the tenant while someone is
watching it, and the narrative value -- "here is signature verification and
deduplication doing their job" -- is available from the recorded history
without one.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import AuthContext, get_current_user
from app.core.deps import get_db
from app.domain.enums import WebhookProcessingStatus
from app.models.webhook_event import WebhookEvent
from app.schemas.provider_events import (
    ProviderEventsResponse,
    ProviderEventStats,
    ProviderEventSummary,
)

router = APIRouter(prefix="/provider-events", tags=["provider-events"])


def _case_id_from_payload(payload: dict) -> str | None:
    """Best-effort case reference carried in the provider's notes.

    Payment Links created by RevLoop carry `notes.revloop_case`. Absent for
    events RevLoop did not originate, which is normal rather than an error.
    """
    if not isinstance(payload, dict):
        return None
    for container in ("payload", "notes"):
        nested = payload.get(container)
        if isinstance(nested, dict) and isinstance(nested.get("revloop_case"), str):
            return nested["revloop_case"]
    entity = payload.get("payload")
    if isinstance(entity, dict):
        for value in entity.values():
            if isinstance(value, dict):
                inner = value.get("entity")
                if isinstance(inner, dict):
                    notes = inner.get("notes")
                    if isinstance(notes, dict) and isinstance(
                        notes.get("revloop_case"), str
                    ):
                        return notes["revloop_case"]
    return None


@router.get("", response_model=ProviderEventsResponse)
def list_provider_events(
    current_user: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> ProviderEventsResponse:
    """Recent webhook events for the caller's organization, newest first.

    Every role may read this. It reveals nothing a member of the organization
    cannot already see, and the audit value of the view depends on operators
    being able to look at it without an elevated role.
    """
    organization_id = current_user.organization_id

    rows = list(
        session.execute(
            select(WebhookEvent)
            .where(WebhookEvent.organization_id == organization_id)
            .order_by(WebhookEvent.received_at.desc())
            .limit(limit)
        ).scalars()
    )

    # Counted over the whole tenant rather than the returned page, so the
    # summary describes the traffic instead of the last 25 rows.
    status_counts = dict(
        session.execute(
            select(WebhookEvent.processing_status, func.count())
            .where(WebhookEvent.organization_id == organization_id)
            .group_by(WebhookEvent.processing_status)
        ).all()
    )
    total = int(
        session.execute(
            select(func.count())
            .select_from(WebhookEvent)
            .where(WebhookEvent.organization_id == organization_id)
        ).scalar_one()
    )
    valid = int(
        session.execute(
            select(func.count())
            .select_from(WebhookEvent)
            .where(
                WebhookEvent.organization_id == organization_id,
                WebhookEvent.signature_valid.is_(True),
            )
        ).scalar_one()
    )

    # A duplicate never creates a second row -- the unique constraint on
    # (provider, provider_event_id) prevents it -- so suppressed duplicates are
    # counted as events whose id was already present when they arrived. That is
    # recorded as an IGNORED status by the ingestion path.
    ignored = int(status_counts.get(WebhookProcessingStatus.IGNORED.value, 0))

    seen: set[tuple[str, str]] = set()
    events: list[ProviderEventSummary] = []
    for row in rows:
        key = (row.provider, row.provider_event_id)
        events.append(
            ProviderEventSummary(
                provider=row.provider,
                provider_event_id=row.provider_event_id,
                event_type=row.event_type,
                received_at=row.received_at,
                processed_at=row.processed_at,
                signature_valid=bool(row.signature_valid),
                processing_status=row.processing_status,
                processing_error=row.processing_error,
                duplicate_of_earlier_event=key in seen,
                case_id=_case_id_from_payload(row.payload or {}),
            )
        )
        seen.add(key)

    return ProviderEventsResponse(
        stats=ProviderEventStats(
            total=total,
            signature_valid=valid,
            signature_rejected=total - valid,
            processed=int(status_counts.get(WebhookProcessingStatus.PROCESSED.value, 0)),
            ignored=ignored,
            failed=int(status_counts.get(WebhookProcessingStatus.FAILED.value, 0)),
            duplicates_suppressed=ignored,
        ),
        events=events,
    )
