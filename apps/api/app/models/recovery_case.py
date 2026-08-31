from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    desc,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import CHAR, BigInteger, DateTime, Numeric

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.domain.enums import CaseType, RecoveryCaseStatus
from app.models._types import enum_check

if TYPE_CHECKING:
    from app.models.audit_log import AuditLog
    from app.models.customer import Customer
    from app.models.invoice import Invoice
    from app.models.organization import Organization
    from app.models.recovery_action import RecoveryAction
    from app.models.recovery_outcome import RecoveryOutcome
    from app.models.recovery_recommendation import RecoveryRecommendation
    from app.models.subscription import Subscription
    from app.models.transaction import Transaction


class RecoveryCase(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "recovery_cases"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "source_event_key",
            name="uq_recovery_cases_organization_id_source_event_key",
        ),
        UniqueConstraint("id", "organization_id", name="uq_recovery_cases_id_organization_id"),
        CheckConstraint("amount_at_risk_minor > 0", name="amount_at_risk_minor_positive"),
        CheckConstraint(
            "expected_recoverable_minor IS NULL OR expected_recoverable_minor >= 0",
            name="expected_recoverable_minor_nonneg",
        ),
        CheckConstraint(
            "priority_score IS NULL OR (priority_score >= 0 AND priority_score <= 1)",
            name="priority_score_range",
        ),
        CheckConstraint(
            "recovery_probability IS NULL OR "
            "(recovery_probability >= 0 AND recovery_probability <= 1)",
            name="recovery_probability_range",
        ),
        CheckConstraint("version >= 1", name="version_min"),
        CheckConstraint(
            "(case_type != 'PAYMENT_FAILURE') OR "
            "(transaction_id IS NOT NULL AND subscription_id IS NULL)",
            name="payment_failure_source",
        ),
        CheckConstraint(
            "(case_type != 'SUBSCRIPTION_FAILURE') OR (subscription_id IS NOT NULL)",
            name="subscription_failure_source",
        ),
        enum_check("case_type", CaseType, "case_type"),
        enum_check("status", RecoveryCaseStatus, "status"),
        Index(
            "ix_recovery_cases_org_status_priority_score",
            "organization_id",
            "status",
            desc("priority_score"),
        ),
        Index(
            "ix_recovery_cases_organization_id_opened_at",
            "organization_id",
            desc("opened_at"),
        ),
        Index(
            "ix_recovery_cases_org_customer_opened_at",
            "organization_id",
            "customer_id",
            desc("opened_at"),
        ),
        Index("ix_recovery_cases_transaction_id", "transaction_id"),
        Index("ix_recovery_cases_subscription_id", "subscription_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customers.id"),
        nullable=False,
    )
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("transactions.id"),
        nullable=True,
    )
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("subscriptions.id"),
        nullable=True,
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("invoices.id"),
        nullable=True,
    )
    source_event_key: Mapped[str] = mapped_column(String(200), nullable=False)
    case_type: Mapped[str] = mapped_column(String(48), nullable=False)
    amount_at_risk_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    failure_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=RecoveryCaseStatus.DETECTED.value
    )
    priority_score: Mapped[Decimal | None] = mapped_column(Numeric(7, 6), nullable=True)
    recovery_probability: Mapped[Decimal | None] = mapped_column(Numeric(7, 6), nullable=True)
    expected_recoverable_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    current_analysis_run_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_transition_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))

    organization: Mapped[Organization] = relationship(back_populates="recovery_cases")
    customer: Mapped[Customer] = relationship(back_populates="recovery_cases")
    transaction: Mapped[Transaction | None] = relationship(back_populates="recovery_cases")
    subscription: Mapped[Subscription | None] = relationship(back_populates="recovery_cases")
    invoice: Mapped[Invoice | None] = relationship(back_populates="recovery_cases")
    recommendations: Mapped[list[RecoveryRecommendation]] = relationship(
        back_populates="case",
        foreign_keys="RecoveryRecommendation.case_id",
    )
    actions: Mapped[list[RecoveryAction]] = relationship(
        back_populates="case",
        foreign_keys="RecoveryAction.case_id",
    )
    outcome: Mapped[RecoveryOutcome | None] = relationship(
        back_populates="case",
        uselist=False,
        foreign_keys="RecoveryOutcome.case_id",
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(
        back_populates="case",
        overlaps="organization,audit_logs",
    )


def tenant_case_fk(table_name: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["case_id", "organization_id"],
        ["recovery_cases.id", "recovery_cases.organization_id"],
        name=f"fk_{table_name}_recovery_cases_tenant",
    )
