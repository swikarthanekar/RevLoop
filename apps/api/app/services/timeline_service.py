"""Audit timeline read services with privacy-safe evidence filtering."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, NotFoundError
from app.repositories.audit_log_repo import AuditLogRepository
from app.repositories.recovery_case_repo import RecoveryCaseRepository
from app.schemas.timeline import TimelineEntry, TimelineResponse

_SENSITIVE_EVIDENCE_KEYS = frozenset(
    {
        "authorization",
        "authorization_header",
        "api_key",
        "secret",
        "password",
        "token",
        "credentials",
        "stack_trace",
        "traceback",
        "raw_payload",
        "webhook_secret",
        "email",
        "phone",
    }
)


def _sanitize_evidence(evidence: dict[str, Any] | None) -> dict[str, Any]:
    if not evidence:
        return {}
    sanitized: dict[str, Any] = {}
    for key, value in evidence.items():
        normalized = key.lower().replace("-", "_")
        if normalized in _SENSITIVE_EVIDENCE_KEYS:
            continue
        if normalized.endswith("_secret") or normalized.endswith("_token"):
            continue
        if isinstance(value, dict):
            nested = _sanitize_evidence(value)
            if nested:
                sanitized[key] = nested
            continue
        sanitized[key] = value
    return sanitized


class TimelineService:
    def __init__(self, session: Session) -> None:
        self._case_repo = RecoveryCaseRepository(session)
        self._audit_repo = AuditLogRepository(session)

    def get_case_timeline(
        self,
        organization_id: UUID,
        case_id: UUID,
    ) -> TimelineResponse:
        if self._case_repo.exists_in_other_organization(case_id, organization_id):
            raise ForbiddenError(
                code="TENANT_ACCESS_DENIED",
                message="Recovery case belongs to another organization.",
            )

        if not self._case_repo.exists_for_organization(case_id, organization_id):
            raise NotFoundError(
                code="CASE_NOT_FOUND",
                message="Recovery case was not found.",
            )

        entries = self._audit_repo.list_for_case(case_id, organization_id)
        return TimelineResponse(
            items=[
                TimelineEntry(
                    id=entry.id,
                    occurred_at=entry.created_at,
                    event_type=entry.event_type,
                    actor_type=entry.actor_type,
                    summary=entry.summary,
                    evidence=_sanitize_evidence(entry.evidence),
                )
                for entry in entries
            ]
        )
