from functools import lru_cache
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import Self

AppEnvironment = Literal["development", "test", "production"]

DEFAULT_DATABASE_URL = "postgresql+psycopg://user:password@localhost:5432/revloop"


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
    public_app_base_url: str = "http://localhost:3000"
    api_version: str = "0.1.0"

    database_url: str = DEFAULT_DATABASE_URL

    dev_auth_user_id: UUID | None = None
    dev_auth_organization_id: UUID | None = None

    supabase_jwt_secret: SecretStr = Field(default=SecretStr("dev-supabase-jwt-secret"))

    razorpay_key_id: SecretStr = Field(default=SecretStr("dev-razorpay-key-id"))
    razorpay_key_secret: SecretStr = Field(default=SecretStr("dev-razorpay-key-secret"))
    razorpay_webhook_secret: SecretStr = Field(default=SecretStr("dev-razorpay-webhook-secret"))

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
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
