"""Authenticated-identity read route.

The frontend needs a way to learn who the current bearer token resolves to
-- organization and role -- after a real Supabase sign-in, since neither of
those live in the JWT itself (see app/core/auth.py::SupabaseAuthBackend).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.auth import AuthContext, get_current_user
from app.schemas.auth import CurrentUserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=CurrentUserResponse)
def get_current_user_identity(
    current_user: Annotated[AuthContext, Depends(get_current_user)],
) -> CurrentUserResponse:
    return CurrentUserResponse(
        user_id=current_user.user_id,
        organization_id=current_user.organization_id,
        role=current_user.role,
    )
