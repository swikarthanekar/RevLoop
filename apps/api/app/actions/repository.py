"""Recovery action persistence (Prompt 16)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.enums import RecoveryActionStatus, RecoveryActionType
from app.models.recovery_action import RecoveryAction
from app.models.recovery_case import RecoveryCase

BLOCKING_ACTION_STATUSES = frozenset(
    {
        RecoveryActionStatus.PENDING_APPROVAL.value,
        RecoveryActionStatus.EXECUTING.value,
        RecoveryActionStatus.UNKNOWN.value,
    }
)


class RecoveryActionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(
        self,
        *,
        action_id: UUID,
        organization_id: UUID,
    ) -> RecoveryAction | None:
        return self._session.execute(
            select(RecoveryAction).where(
                RecoveryAction.id == action_id,
                RecoveryAction.organization_id == organization_id,
            )
        ).scalar_one_or_none()

    def get_by_idempotency_key(
        self,
        idempotency_key: str,
        *,
        organization_id: UUID,
    ) -> RecoveryAction | None:
        # The key is derived from an already org-scoped case_id/recommendation_id
        # (see build_action_idempotency_key), so a cross-tenant collision is not
        # feasible today. The explicit filter is defense-in-depth, matching every
        # other lookup in this repository.
        return self._session.execute(
            select(RecoveryAction).where(
                RecoveryAction.idempotency_key == idempotency_key,
                RecoveryAction.organization_id == organization_id,
            )
        ).scalar_one_or_none()

    def get_blocking_payment_link_action(
        self,
        *,
        case_id: UUID,
        organization_id: UUID,
    ) -> RecoveryAction | None:
        return self._session.execute(
            select(RecoveryAction)
            .where(
                RecoveryAction.case_id == case_id,
                RecoveryAction.organization_id == organization_id,
                RecoveryAction.action_type == RecoveryActionType.CREATE_PAYMENT_LINK.value,
                RecoveryAction.status.in_(tuple(BLOCKING_ACTION_STATUSES)),
            )
            .order_by(RecoveryAction.created_at.desc())
        ).scalar_one_or_none()

    def lock_case(
        self,
        *,
        case_id: UUID,
        organization_id: UUID,
    ) -> RecoveryCase | None:
        return self._session.execute(
            select(RecoveryCase)
            .where(
                RecoveryCase.id == case_id,
                RecoveryCase.organization_id == organization_id,
            )
            .with_for_update()
        ).scalar_one_or_none()

    def next_attempt_number(
        self,
        *,
        case_id: UUID,
        organization_id: UUID,
    ) -> int:
        current_max = self._session.execute(
            select(func.max(RecoveryAction.attempt_number)).where(
                RecoveryAction.case_id == case_id,
                RecoveryAction.organization_id == organization_id,
            )
        ).scalar_one()
        return int(current_max or 0) + 1

    def count_actions(self, *, case_id: UUID, organization_id: UUID) -> int:
        return int(
            self._session.execute(
                select(func.count())
                .select_from(RecoveryAction)
                .where(
                    RecoveryAction.case_id == case_id,
                    RecoveryAction.organization_id == organization_id,
                )
            ).scalar_one()
        )

    def add(self, action: RecoveryAction) -> RecoveryAction:
        self._session.add(action)
        self._session.flush()
        return action
