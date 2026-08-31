"""Repository for tenant-scoped audit timeline reads."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


class AuditLogRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_case(
        self,
        case_id: UUID,
        organization_id: UUID,
    ) -> list[AuditLog]:
        return list(
            self._session.execute(
                select(AuditLog)
                .where(
                    AuditLog.case_id == case_id,
                    AuditLog.organization_id == organization_id,
                )
                .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
            ).scalars()
        )
