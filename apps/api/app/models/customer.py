from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import BigInteger

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.recovery_case import RecoveryCase
    from app.models.subscription import Subscription
    from app.models.transaction import Transaction


class Customer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "external_id",
            name="uq_customers_organization_id_external_id",
        ),
        CheckConstraint("lifetime_value_minor >= 0", name="lifetime_value_minor_nonneg"),
        Index("ix_customers_organization_id_segment", "organization_id", "segment"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
    )
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    segment: Mapped[str] = mapped_column(String(32), nullable=False, server_default="REGULAR")
    lifetime_value_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_synthetic: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    organization: Mapped[Organization] = relationship(back_populates="customers")
    transactions: Mapped[list[Transaction]] = relationship(back_populates="customer")
    subscriptions: Mapped[list[Subscription]] = relationship(back_populates="customer")
    recovery_cases: Mapped[list[RecoveryCase]] = relationship(back_populates="customer")
