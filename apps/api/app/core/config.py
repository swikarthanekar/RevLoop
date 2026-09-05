from functools import lru_cache
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import Self

AppEnvironment = Literal["development", "test", "production"]

DEFAULT_DATABASE_URL = "postgresql+psycopg://user:password@localhost:5432/revloop"

#: Canonical Razorpay API host. Production is pinned to this value.
RAZORPAY_DEFAULT_API_BASE_URL = "https://api.razorpay.com"


def normalize_database_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: AppEnvironment = "development"
    demo_mode: bool = True
    #: Second, independent switch that permits `POST /api/v1/demo/reset` to
    #: destroy and rebuild the demo tenant while `APP_ENV=production`.
    #:
    #: `DEMO_MODE` alone is not enough on purpose. Demo mode is on in the
    #: deployed environment so the demo *routes* exist, and reset is the one
    #: demo operation that deletes rows. Requiring a separate opt-in means the
    #: destructive path cannot be reached by flipping a single flag that is
    #: already on, and turning it off leaves the rest of the demo surface
    #: working. Outside production the flag is not consulted, so local and test
    #: environments keep resetting freely.
    demo_reset_enabled: bool = False
    public_app_base_url: str = "http://localhost:3000"
    api_version: str = "0.1.0"

    database_url: str = DEFAULT_DATABASE_URL

    dev_auth_user_id: UUID | None = None
    dev_auth_organization_id: UUID | None = None

    supabase_jwt_secret: SecretStr = Field(default=SecretStr("dev-supabase-jwt-secret"))
    #: Required only for a Supabase project using asymmetric JWT signing
    #: keys (ES256/RS256, verified via JWKS) rather than the legacy shared
    #: HS256 secret above -- see SupabaseAuthBackend. Not a secret: it's the
    #: same value already public in the frontend's NEXT_PUBLIC_SUPABASE_URL.
    supabase_url: str | None = None

    razorpay_key_id: SecretStr = Field(default=SecretStr("dev-razorpay-key-id"))
    razorpay_key_secret: SecretStr = Field(default=SecretStr("dev-razorpay-key-secret"))
    razorpay_webhook_secret: SecretStr = Field(default=SecretStr("dev-razorpay-webhook-secret"))

    # Overridable only outside production, so automated tests can point the real
    # client at a local stub. Production is pinned to the canonical host below.
    razorpay_api_base_url: str = RAZORPAY_DEFAULT_API_BASE_URL

    llm_provider: str = "gemini"
    gemini_api_key: SecretStr | None = Field(default=None)
    gemini_model_name: str = "gemini-3.6-flash"
    gemini_timeout_seconds: float = 3.0

    model_bundle_path: Path = Path("./models/recovery_model_v1.joblib")

    log_level: str = "INFO"

    @field_validator("database_url")
    @classmethod
    def normalize_database_url_value(cls, value: str) -> str:
        return normalize_database_url(value)

    @field_validator("app_env", mode="before")
    @classmethod
    def normalize_app_env(cls, value: object) -> object:
        if isinstance(value, str):
            return value.lower()
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @model_validator(mode="after")
    def validate_production_secrets(self) -> Self:
        if not self.is_production:
            return self

        missing: list[str] = []
        if self.supabase_jwt_secret.get_secret_value().startswith("dev-"):
            missing.append("SUPABASE_JWT_SECRET")
        if self.razorpay_key_id.get_secret_value().startswith("dev-"):
            missing.append("RAZORPAY_KEY_ID")
        if self.razorpay_key_secret.get_secret_value().startswith("dev-"):
            missing.append("RAZORPAY_KEY_SECRET")
        if self.razorpay_webhook_secret.get_secret_value().startswith("dev-"):
            missing.append("RAZORPAY_WEBHOOK_SECRET")
        if missing:
            raise ValueError(
                f"Production environment requires real values for: {', '.join(missing)}"
            )
        if self.razorpay_api_base_url.rstrip("/") != RAZORPAY_DEFAULT_API_BASE_URL:
            raise ValueError(
                "Production environment must use the canonical Razorpay API base URL "
                f"({RAZORPAY_DEFAULT_API_BASE_URL}); RAZORPAY_API_BASE_URL cannot be overridden."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
