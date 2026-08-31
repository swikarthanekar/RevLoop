from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import CHAR, BigInteger, DateTime

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.organization import Organization
    from app.models.recovery_case import RecoveryCase


class Invoice(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """P1 schema reservation — no API or workflow behavior in Milestone 2."""

    __tablename__ = "invoices"
    __table_args__ = (
        CheckConstraint("amount_due_minor >= 0", name="amount_due_minor_nonneg"),
        CheckConstraint("amount_paid_minor >= 0", name="amount_paid_minor_nonneg"),
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
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_invoice_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    amount_due_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount_paid_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_synthetic: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    organization: Mapped[Organization] = relationship()
    customer: Mapped[Customer] = relationship()
    recovery_cases: Mapped[list[RecoveryCase]] = relationship(back_populates="invoice")
