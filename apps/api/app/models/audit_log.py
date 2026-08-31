from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, ForeignKeyConstraint, Index, String, Text, desc, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.domain.enums import AuditActorType
from app.models._types import enum_check

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.recovery_case import RecoveryCase


class AuditLog(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        enum_check("actor_type", AuditActorType, "actor_type"),
        ForeignKeyConstraint(
            ["case_id", "organization_id"],
            ["recovery_cases.id", "recovery_cases.organization_id"],
            name="fk_audit_logs_recovery_cases_tenant",
        ),
        Index(
            "ix_audit_logs_organization_id_created_at",
            "organization_id",
            desc("created_at"),
        ),
        Index("ix_audit_logs_case_id_created_at", "case_id", "created_at"),
        Index(
            "ix_audit_logs_org_event_type_created_at",
            "organization_id",
            "event_type",
            desc("created_at"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
    )
    case_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    organization: Mapped[Organization] = relationship(
        back_populates="audit_logs",
        overlaps="case,audit_logs",
    )
    case: Mapped[RecoveryCase | None] = relationship(
        back_populates="audit_logs",
        foreign_keys=[case_id, organization_id],
        overlaps="organization,audit_logs",
    )
