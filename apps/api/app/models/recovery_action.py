from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import DateTime

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.domain.enums import RecoveryActionStatus, RecoveryActionType
from app.models._types import enum_check
from app.models.recovery_case import tenant_case_fk

if TYPE_CHECKING:
    from app.models.recovery_case import RecoveryCase


class RecoveryAction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "recovery_actions"
    __table_args__ = (
        tenant_case_fk("recovery_actions"),
        UniqueConstraint("idempotency_key", name="uq_recovery_actions_idempotency_key"),
        UniqueConstraint(
            "case_id",
            "attempt_number",
            name="uq_recovery_actions_case_id_attempt_number",
        ),
        CheckConstraint("attempt_number >= 1", name="attempt_number_min"),
        enum_check("action_type", RecoveryActionType, "action_type"),
        enum_check("status", RecoveryActionStatus, "status"),
        Index(
            "ix_recovery_actions_org_status_scheduled_for",
            "organization_id",
            "status",
            "scheduled_for",
        ),
        Index("ix_recovery_actions_case_id_created_at", "case_id", "created_at"),
        Index(
            "uq_recovery_actions_one_executing",
            "case_id",
            unique=True,
            postgresql_where=text("status = 'EXECUTING'"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    case_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    recommendation_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    request_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_reference: Mapped[str | None] = mapped_column(String(160), nullable=True)
    provider_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    case: Mapped[RecoveryCase] = relationship(
        back_populates="actions",
        foreign_keys=[case_id, organization_id],
    )
