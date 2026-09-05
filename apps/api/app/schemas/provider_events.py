"""Contracts for the read-only provider-events view.

Webhook handling is where most of the correctness work in this system lives --
HMAC verification over the raw body, deduplication on the provider's own event
id, stale-event precedence -- and none of it was visible anywhere. It ran, it
was tested, and a reviewer had to take it on trust.

This exposes what already happened. It is a read of `webhook_events`: no
replay, no re-processing, no write path. That matters for a live demo, where a
control that re-fires a webhook is a control that can corrupt the tenant while
someone watches.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProviderEventSummary(BaseModel):
    """One received webhook and what the system decided about it."""

    model_config = ConfigDict(frozen=True)

    provider: str
    provider_event_id: str
    event_type: str
    received_at: datetime
    processed_at: datetime | None

    #: Whether the HMAC over the raw request body matched. An event that fails
    #: this is recorded and rejected; it never reaches business logic.
    signature_valid: bool
    processing_status: str
    #: Populated when the event was rejected or ignored, so a viewer can see
    #: *why* rather than only that something did not happen.
    processing_error: str | None = None

    #: True when this event id had already been seen. The duplicate is the
    #: interesting row: it is proof the dedup constraint did its job.
    duplicate_of_earlier_event: bool = False

    #: The case this event affected, when it resolved to one.
    case_id: str | None = None


class ProviderEventStats(BaseModel):
    """Aggregate counts, so the view leads with the shape of the traffic."""

    model_config = ConfigDict(frozen=True)

    total: int = Field(ge=0)
    signature_valid: int = Field(ge=0)
    signature_rejected: int = Field(ge=0)
    processed: int = Field(ge=0)
    ignored: int = Field(ge=0)
    failed: int = Field(ge=0)
    duplicates_suppressed: int = Field(ge=0)


class ProviderEventsResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    stats: ProviderEventStats
    events: list[ProviderEventSummary]
