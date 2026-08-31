"""Transition-safe persistence for recovery cases."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.domain.enums import RecoveryCaseStatus
from app.models.recovery_case import RecoveryCase
from app.models.recovery_outcome import RecoveryOutcome


class RecoveryCaseWorkflowRepository:
    def get_case(
        self,
        session: Session,
        *,
        case_id: UUID,
        organization_id: UUID,
    ) -> RecoveryCase | None:
        return session.execute(
            select(RecoveryCase).where(
                RecoveryCase.id == case_id,
                RecoveryCase.organization_id == organization_id,
            )
        ).scalar_one_or_none()

    def has_recovered_outcome(
        self,
        session: Session,
        *,
        case_id: UUID,
        organization_id: UUID,
    ) -> bool:
        outcome = session.execute(
            select(RecoveryOutcome.id).where(
                RecoveryOutcome.case_id == case_id,
                RecoveryOutcome.organization_id == organization_id,
                RecoveryOutcome.outcome == "RECOVERED",
                RecoveryOutcome.recovered_amount_minor > 0,
            )
        ).scalar_one_or_none()
        return outcome is not None

    def persist_transition(
        self,
        session: Session,
        *,
        case_id: UUID,
        organization_id: UUID,
        expected_version: int,
        new_status: RecoveryCaseStatus,
        transition_at: datetime,
        resolved_at: datetime | None,
    ) -> int:
        values: dict = {
            "status": new_status.value,
            "version": expected_version + 1,
            "last_transition_at": transition_at,
            "updated_at": transition_at,
        }
        if resolved_at is not None:
            values["resolved_at"] = resolved_at

        result = session.execute(
            update(RecoveryCase)
            .where(
                RecoveryCase.id == case_id,
                RecoveryCase.organization_id == organization_id,
                RecoveryCase.version == expected_version,
            )
            .values(**values)
        )
        return int(result.rowcount or 0)
