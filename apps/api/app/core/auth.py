from typing import Protocol
from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict

from app.core.config import Settings, get_settings
from app.domain.enums import UserRole

security = HTTPBearer(auto_error=False)

DEV_TEST_USER_ID = UUID("00000000-0000-4000-8000-000000000001")
DEV_TEST_ORG_ID = UUID("00000000-0000-4000-8000-000000000010")


class AuthContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: UUID
    organization_id: UUID
    role: UserRole


class AuthBackend(Protocol):
    def resolve(self, token: str | None) -> AuthContext: ...


class DevAuthBackend:
    """Temporary auth for development and automated tests."""

    def resolve(self, token: str | None) -> AuthContext:
        if token is None:
            raise HTTPException(
                status_code=401,
                detail={"code": "UNAUTHORIZED", "message": "Authentication required."},
            )

        if token == "dev-analyst":
            return AuthContext(
                user_id=DEV_TEST_USER_ID,
                organization_id=DEV_TEST_ORG_ID,
                role=UserRole.ANALYST,
            )
        if token == "dev-operator":
            return AuthContext(
                user_id=DEV_TEST_USER_ID,
                organization_id=DEV_TEST_ORG_ID,
                role=UserRole.OPERATOR,
            )
        if token == "dev-admin":
            return AuthContext(
                user_id=DEV_TEST_USER_ID,
                organization_id=DEV_TEST_ORG_ID,
                role=UserRole.ADMIN,
            )

        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED", "message": "Invalid authentication token."},
        )


class SupabaseAuthBackend:
    """Placeholder for future Supabase JWT verification."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def resolve(self, token: str | None) -> AuthContext:
        raise HTTPException(
            status_code=501,
            detail={
                "code": "AUTH_NOT_CONFIGURED",
                "message": "Supabase authentication is not configured yet.",
            },
        )


def get_auth_backend(settings: Settings = Depends(get_settings)) -> AuthBackend:
    if settings.app_env in ("development", "test"):
        return DevAuthBackend()
    return SupabaseAuthBackend(settings)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    backend: AuthBackend = Depends(get_auth_backend),
) -> AuthContext:
    token = credentials.credentials if credentials else None
    return backend.resolve(token)


async def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    backend: AuthBackend = Depends(get_auth_backend),
) -> AuthContext | None:
    if credentials is None:
        return None
    return backend.resolve(credentials.credentials)
