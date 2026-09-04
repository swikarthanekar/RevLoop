"""Schemas for the authenticated-identity route."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from app.domain.enums import UserRole


class CurrentUserResponse(BaseModel):
    user_id: UUID
    organization_id: UUID
    role: UserRole
