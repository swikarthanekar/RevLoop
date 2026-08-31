from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import BigInteger, DateTime

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.domain.enums import RecoveryOutcomeType, VerificationSource
from app.models._types import enum_check
from app.models.recovery_case import tenant_case_fk

if TYPE_CHECKING:
    from app.models.recovery_case import RecoveryCase


class RecoveryOutcome(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "recovery_outcomes"
    __table_args__ = (
        tenant_case_fk("recovery_outcomes"),
        ForeignKeyConstraint(
            ["verified_event_id"],
            ["webhook_events.id"],
            name="fk_recovery_outcomes_verified_event_id_webhook_events",
            use_alter=True,
        ),
        UniqueConstraint("case_id", name="uq_recovery_outcomes_case_id"),
        CheckConstraint("recovered_amount_minor >= 0", name="recovered_amount_minor_nonneg"),
        CheckConstraint(
            "(outcome != 'RECOVERED') OR (recovered_amount_minor > 0)",
            name="recovered_outcome_amount_positive",
        ),
        enum_check("outcome", RecoveryOutcomeType, "outcome"),
        enum_check("verification_source", VerificationSource, "verification_source"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    case_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    recovered_amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    recovered_payment_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    verification_source: Mapped[str] = mapped_column(String(32), nullable=False)
    verified_event_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    recovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    time_to_recovery_seconds: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    case: Mapped[RecoveryCase] = relationship(
        back_populates="outcome",
        foreign_keys=[case_id, organization_id],
    )
