"""Webhook event persistence with database-backed idempotency."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.domain.enums import WebhookProcessingStatus
from app.models.webhook_event import WebhookEvent

PROVIDER_RAZORPAY = "razorpay"

ClaimStatus = Literal["new", "retriable", "complete"]

_TERMINAL_STATUSES = frozenset(
    {
        WebhookProcessingStatus.PROCESSED.value,
        WebhookProcessingStatus.IGNORED.value,
    }
)
_RETRIABLE_STATUSES = frozenset(
    {
        WebhookProcessingStatus.RECEIVED.value,
        WebhookProcessingStatus.FAILED.value,
    }
)


class WebhookEventRepository:
    def get_by_provider_event_id(
        self,
        session: Session,
        *,
        provider: str,
        provider_event_id: str,
    ) -> WebhookEvent | None:
        return session.execute(
            select(WebhookEvent).where(
                WebhookEvent.provider == provider,
                WebhookEvent.provider_event_id == provider_event_id,
            )
        ).scalar_one_or_none()

    def claim_event(
        self,
        session: Session,
        *,
        organization_id: UUID,
        provider: str,
        provider_event_id: str,
        event_type: str,
        provider_created_at: datetime | None,
        payload: dict,
        received_at: datetime,
    ) -> tuple[WebhookEvent, ClaimStatus]:
        """Insert RECEIVED or return existing with claim disposition."""
        stmt = (
            insert(WebhookEvent)
            .values(
                organization_id=organization_id,
                provider=provider,
                provider_event_id=provider_event_id,
                event_type=event_type,
                provider_created_at=provider_created_at,
                signature_valid=True,
                processing_status=WebhookProcessingStatus.RECEIVED.value,
                payload=payload,
                received_at=received_at,
            )
            .on_conflict_do_nothing(
                index_elements=["provider", "provider_event_id"],
            )
            .returning(WebhookEvent.id)
        )
        inserted_id = session.execute(stmt).scalar_one_or_none()
        if inserted_id is not None:
            event = session.get(WebhookEvent, inserted_id)
            if event is None:
                raise RuntimeError("Inserted webhook event not found.")
            return event, "new"

        existing = self.get_by_provider_event_id(
            session,
            provider=provider,
            provider_event_id=provider_event_id,
        )
        if existing is None:
            raise RuntimeError("Webhook duplicate conflict without existing row.")
        if existing.processing_status in _TERMINAL_STATUSES:
            return existing, "complete"
        if existing.processing_status in _RETRIABLE_STATUSES:
            return existing, "retriable"
        return existing, "retriable"

    def mark_processed(
        self,
        session: Session,
        *,
        event: WebhookEvent,
        processed_at: datetime,
    ) -> None:
        event.processing_status = WebhookProcessingStatus.PROCESSED.value
        event.processed_at = processed_at
        event.processing_error = None
        session.flush()

    def mark_ignored(
        self,
        session: Session,
        *,
        event: WebhookEvent,
        processed_at: datetime,
        reason: str,
    ) -> None:
        event.processing_status = WebhookProcessingStatus.IGNORED.value
        event.processed_at = processed_at
        event.processing_error = reason
        session.flush()

    def mark_failed(
        self,
        session: Session,
        *,
        event: WebhookEvent,
        processed_at: datetime,
        reason: str,
    ) -> None:
        event.processing_status = WebhookProcessingStatus.FAILED.value
        event.processed_at = processed_at
        event.processing_error = reason
        session.flush()
