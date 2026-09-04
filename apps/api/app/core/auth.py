from typing import Protocol
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.deps import get_db
from app.domain.enums import UserRole
from app.models.user_profile import UserProfile

security = HTTPBearer(auto_error=False)

#: The claim Supabase issues on every user access token (as opposed to the
#: anon/service-role keys, which carry a different audience even when
#: signed the same way). Requiring it rejects those other token kinds
#: outright rather than silently trusting a mismatched claim.
SUPABASE_USER_AUDIENCE = "authenticated"

#: Older/unmigrated Supabase projects sign user access tokens with a shared
#: HS256 secret (SUPABASE_JWT_SECRET). Newer projects (and any project that
#: has rotated to "JWT Signing Keys" in the dashboard) sign asymmetrically
#: with ES256, verified against the project's public JWKS document instead
#: -- there is no shared secret to configure for those. The two are not
#: interchangeable and a project uses exactly one at a time; which one is
#: used is read from the token's own `alg` header rather than assumed.
_SYMMETRIC_ALGORITHMS = frozenset({"HS256"})
_ASYMMETRIC_ALGORITHMS = frozenset({"ES256", "RS256"})

#: PyJWKClient caches the fetched JWK Set internally (5 minute default
#: lifespan). SupabaseAuthBackend is constructed fresh per request by
#: get_auth_backend, so the client itself is cached here per JWKS URL --
#: otherwise that cache would start empty on every single request.
_jwks_clients: dict[str, PyJWKClient] = {}


def _get_jwks_client(jwks_url: str) -> PyJWKClient:
    client = _jwks_clients.get(jwks_url)
    if client is None:
        client = PyJWKClient(jwks_url)
        _jwks_clients[jwks_url] = client
    return client


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

    `sub` is the Supabase `auth.users.id`. RevLoop's own tenant and role
    model lives in `user_profiles`, keyed by that same id -- Supabase Auth
    answers "who is this", `user_profiles` answers "which organization, with
    what role". A verified token with no matching profile is a real,
    distinct failure (an account that exists in Supabase but was never
    provisioned into an organization), not an authentication failure.
    """

    def __init__(self, settings: Settings, session: Session) -> None:
        self._settings = settings
        self._session = session

    def _resolve_verification_key(self, token: str, algorithm: str) -> str:
        """The key `jwt.decode` verifies `token` against, chosen by `algorithm`."""
        if algorithm in _ASYMMETRIC_ALGORITHMS:
            if not self._settings.supabase_url:
                raise HTTPException(
                    status_code=500,
                    detail={
                        "code": "AUTH_NOT_CONFIGURED",
                        "message": (
                            "SUPABASE_URL must be configured to verify this "
                            "project's JWT signing keys."
                        ),
                    },
                )
            jwks_url = (
                f"{self._settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
            )
            try:
                signing_key = _get_jwks_client(jwks_url).get_signing_key_from_jwt(token)
            except jwt.PyJWKClientConnectionError as exc:
                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": "SERVICE_UNAVAILABLE",
                        "message": "Unable to reach the identity provider. Try again.",
                    },
                ) from exc
            except jwt.PyJWKClientError as exc:
                raise HTTPException(
                    status_code=401,
                    detail={"code": "UNAUTHORIZED", "message": "Invalid authentication token."},
                ) from exc
            return signing_key.key
        return self._settings.supabase_jwt_secret.get_secret_value()

    def resolve(self, token: str | None) -> AuthContext:
        if token is None:
            raise HTTPException(
                status_code=401,
                detail={"code": "UNAUTHORIZED", "message": "Authentication required."},
            )

        try:
            algorithm = jwt.get_unverified_header(token).get("alg")
        except jwt.InvalidTokenError as exc:
            raise HTTPException(
                status_code=401,
                detail={"code": "UNAUTHORIZED", "message": "Invalid authentication token."},
            ) from exc
        if algorithm not in _SYMMETRIC_ALGORITHMS and algorithm not in _ASYMMETRIC_ALGORITHMS:
            raise HTTPException(
                status_code=401,
                detail={"code": "UNAUTHORIZED", "message": "Invalid authentication token."},
            )

        key = self._resolve_verification_key(token, algorithm)
        try:
            payload = jwt.decode(
                token,
                key,
                algorithms=[algorithm],
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
