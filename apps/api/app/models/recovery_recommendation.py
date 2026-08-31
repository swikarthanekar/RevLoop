from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import BigInteger, Numeric

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.domain.enums import RecoveryActionType
from app.models._types import enum_check
from app.models.recovery_case import tenant_case_fk

if TYPE_CHECKING:
    from app.models.recovery_case import RecoveryCase


class RecoveryRecommendation(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "recovery_recommendations"
    __table_args__ = (
        tenant_case_fk("recovery_recommendations"),
        UniqueConstraint(
            "case_id",
            "analysis_run_id",
            "action_type",
            name="uq_recovery_recommendations_case_analysis_action",
        ),
        UniqueConstraint(
            "case_id",
            "analysis_run_id",
            "rank",
            name="uq_recovery_recommendations_case_analysis_rank",
        ),
        CheckConstraint("rank > 0", name="rank_positive"),
        CheckConstraint(
            "success_probability >= 0 AND success_probability <= 1",
            name="success_probability_range",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        enum_check("action_type", RecoveryActionType, "action_type"),
        Index(
            "ix_recovery_recommendations_case_analysis_rank",
            "case_id",
            "analysis_run_id",
            "rank",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    case_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    success_probability: Mapped[Decimal] = mapped_column(Numeric(7, 6), nullable=False)
    expected_recovered_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expected_value_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(7, 6), nullable=False)
    policy_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False)
    policy_reasons: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    factors: Mapped[list[dict[str, str]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    feature_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)

    case: Mapped[RecoveryCase] = relationship(
        back_populates="recommendations",
        foreign_keys=[case_id, organization_id],
    )
