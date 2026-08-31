from typing import Protocol
from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict

from app.core.config import Settings, get_settings
from app.domain.enums import UserRole

security = HTTPBearer(auto_error=False)


class AuthContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: UUID
    organization_id: UUID
    role: UserRole


class AuthBackend(Protocol):
    def resolve(self, token: str | None) -> AuthContext: ...


class DevAuthBackend:
    """Temporary auth for development and automated tests."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def resolve(self, token: str | None) -> AuthContext:
        if token is None:
            raise HTTPException(
                status_code=401,
                detail={"code": "UNAUTHORIZED", "message": "Authentication required."},
            )

        role: UserRole | None = None
        if token == "dev-analyst":
            role = UserRole.ANALYST
        elif token == "dev-operator":
            role = UserRole.OPERATOR
        elif token == "dev-admin":
            role = UserRole.ADMIN

        if role is None:
            raise HTTPException(
                status_code=401,
                detail={"code": "UNAUTHORIZED", "message": "Invalid authentication token."},
            )

        user_id = self._settings.dev_auth_user_id
        organization_id = self._settings.dev_auth_organization_id
        if user_id is None or organization_id is None:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "AUTH_NOT_CONFIGURED",
                    "message": (
                        "Development auth requires DEV_AUTH_USER_ID and "
                        "DEV_AUTH_ORGANIZATION_ID to be configured."
                    ),
                },
            )

        return AuthContext(
            user_id=user_id,
            organization_id=organization_id,
            role=role,
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
        return DevAuthBackend(settings)
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
