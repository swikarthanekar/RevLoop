from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.domain.enums import UserRole
from app.models._types import enum_check

if TYPE_CHECKING:
    from app.models.organization import Organization


class UserProfile(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "user_profiles"
    __table_args__ = (
        UniqueConstraint("auth_user_id", name="uq_user_profiles_auth_user_id"),
        enum_check("role", UserRole, "role"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    auth_user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)

    organization: Mapped[Organization] = relationship(back_populates="user_profiles")
