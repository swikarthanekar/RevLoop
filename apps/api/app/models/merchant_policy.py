from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import BigInteger, Numeric

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.organization import Organization


class MerchantPolicy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "merchant_policies"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_merchant_policies_organization_id"),
        CheckConstraint("auto_action_limit_minor >= 0", name="auto_action_limit_minor_nonneg"),
        CheckConstraint("max_recovery_attempts >= 0", name="max_recovery_attempts_nonneg"),
        CheckConstraint("max_contacts_per_24h >= 0", name="max_contacts_per_24h_nonneg"),
        CheckConstraint("cooldown_minutes >= 0", name="cooldown_minutes_nonneg"),
        CheckConstraint(
            "minimum_auto_confidence >= 0 AND minimum_auto_confidence <= 1",
            name="minimum_auto_confidence_range",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
    )
    auto_action_limit_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    max_recovery_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    max_contacts_per_24h: Mapped[int] = mapped_column(Integer, nullable=False)
    minimum_auto_confidence: Mapped[Decimal] = mapped_column(Numeric(7, 6), nullable=False)
    cooldown_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    automation_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    allowed_action_types: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )

    organization: Mapped[Organization] = relationship(back_populates="merchant_policy")
