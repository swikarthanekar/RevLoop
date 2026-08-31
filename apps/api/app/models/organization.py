from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import CHAR

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.audit_log import AuditLog
    from app.models.customer import Customer
    from app.models.merchant_policy import MerchantPolicy
    from app.models.recovery_case import RecoveryCase
    from app.models.subscription import Subscription
    from app.models.transaction import Transaction
    from app.models.user_profile import UserProfile
    from app.models.webhook_event import WebhookEvent


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False, server_default="INR")
    automation_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )

    user_profiles: Mapped[list[UserProfile]] = relationship(back_populates="organization")
    customers: Mapped[list[Customer]] = relationship(back_populates="organization")
    transactions: Mapped[list[Transaction]] = relationship(back_populates="organization")
    subscriptions: Mapped[list[Subscription]] = relationship(back_populates="organization")
    recovery_cases: Mapped[list[RecoveryCase]] = relationship(back_populates="organization")
    webhook_events: Mapped[list[WebhookEvent]] = relationship(back_populates="organization")
    audit_logs: Mapped[list[AuditLog]] = relationship(
        back_populates="organization",
        overlaps="case",
    )
    merchant_policy: Mapped[MerchantPolicy | None] = relationship(
        back_populates="organization", uselist=False
    )
