from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class TimelineEntry(BaseModel):
    id: UUID
    occurred_at: datetime
    event_type: str
    actor_type: str
    summary: str
    evidence: dict[str, Any]


class TimelineResponse(BaseModel):
    items: list[TimelineEntry]
