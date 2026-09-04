from typing import Protocol
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.deps import get_db
from app.domain.enums import UserRole
from app.models.user_profile import UserProfile

security = HTTPBearer(auto_error=False)

#: The claim Supabase issues on every user access token (as opposed to the
#: anon/service-role keys, which are also HS256-signed with the same project
#: secret but carry a different audience). Requiring it rejects those other
#: token kinds outright rather than silently trusting a mismatched claim.
SUPABASE_USER_AUDIENCE = "authenticated"


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
    """Verifies a Supabase Auth access token and resolves it to a tenant.

    Supabase signs user access tokens with the project's JWT secret
    (HS256); `sub` is the Supabase `auth.users.id`. RevLoop's own tenant and
    role model lives in `user_profiles`, keyed by that same id -- Supabase
    Auth answers "who is this", `user_profiles` answers "which organization,
    with what role". A verified token with no matching profile is a real,
    distinct failure (an account that exists in Supabase but was never
    provisioned into an organization), not an authentication failure.
    """

    def __init__(self, settings: Settings, session: Session) -> None:
        self._settings = settings
        self._session = session

    def resolve(self, token: str | None) -> AuthContext:
        if token is None:
            raise HTTPException(
                status_code=401,
                detail={"code": "UNAUTHORIZED", "message": "Authentication required."},
            )

        secret = self._settings.supabase_jwt_secret.get_secret_value()
        try:
            payload = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                audience=SUPABASE_USER_AUDIENCE,
            )
        except jwt.ExpiredSignatureError as exc:
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "TOKEN_EXPIRED",
                    "message": "Session expired. Please sign in again.",
                },
            ) from exc
        except jwt.InvalidTokenError as exc:
            raise HTTPException(
                status_code=401,
                detail={"code": "UNAUTHORIZED", "message": "Invalid authentication token."},
            ) from exc

        subject = payload.get("sub")
        try:
            auth_user_id = UUID(str(subject))
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=401,
                detail={"code": "UNAUTHORIZED", "message": "Invalid authentication token."},
            ) from exc

        profile = self._session.execute(
            select(UserProfile).where(UserProfile.auth_user_id == auth_user_id)
        ).scalar_one_or_none()
        if profile is None:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "NO_ORGANIZATION_MEMBERSHIP",
                    "message": "This account is not linked to a RevLoop organization.",
                },
            )

        return AuthContext(
            user_id=auth_user_id,
            organization_id=profile.organization_id,
            role=UserRole(profile.role),
        )


def get_auth_backend(
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> AuthBackend:
    if settings.app_env in ("development", "test"):
        return DevAuthBackend(settings)
    return SupabaseAuthBackend(settings, db)


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
