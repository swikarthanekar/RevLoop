"""Transition audit persistence."""

from __future__ import annotations

import uuid
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.domain.enums import AuditActorType
from app.models.audit_log import AuditLog


class AuditLogWorkflowRepository:
    def insert_transition_audit(
        self,
        session: Session,
        *,
        organization_id: UUID,
        case_id: UUID,
        actor_type: AuditActorType,
        actor_id: str | None,
        event_type: str,
        summary: str,
        evidence: dict[str, Any],
        audit_id: UUID | None = None,
    ) -> AuditLog:
        audit = AuditLog(
            id=audit_id or uuid.uuid4(),
            organization_id=organization_id,
            case_id=case_id,
            actor_type=actor_type.value,
            actor_id=actor_id,
            event_type=event_type,
            summary=summary,
            evidence=evidence,
        )
        session.add(audit)
        session.flush()
        return audit

    def count_case_audits(
        self,
        session: Session,
        *,
        case_id: UUID,
        organization_id: UUID,
        event_type: str | None = None,
    ) -> int:
        from sqlalchemy import func, select

        stmt = (
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.case_id == case_id,
                AuditLog.organization_id == organization_id,
            )
        )
        if event_type is not None:
            stmt = stmt.where(AuditLog.event_type == event_type)
        return int(session.execute(stmt).scalar_one())
