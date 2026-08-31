import pytest

from app.core.config import Settings, get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_settings_development_defaults() -> None:
    settings = Settings(
        _env_file=None,
        app_env="development",
        demo_mode=True,
    )

    assert settings.app_env == "development"
    assert settings.demo_mode is True
    assert settings.api_version == "0.1.0"
    assert settings.database_url.startswith("postgresql+psycopg://")
    assert settings.llm_provider == "gemini"


def test_settings_secrets_are_not_exposed_in_repr() -> None:
    settings = Settings(
        _env_file=None,
        razorpay_key_secret="super-secret-value",
    )

    rendered = repr(settings.razorpay_key_secret)
    assert "super-secret-value" not in rendered


def test_logging_redacts_secret_like_messages() -> None:
    from app.core.logging import _redact_secrets

    message = "Authorization: Bearer abc123 api_key=secret-value"
    redacted = _redact_secrets(message)

    assert "abc123" not in redacted
    assert "secret-value" not in redacted
    assert "[REDACTED]" in redacted


def test_settings_production_rejects_dev_secret_placeholders() -> None:
    with pytest.raises(ValueError, match="Production environment requires real values"):
        Settings(
            _env_file=None,
            app_env="production",
            supabase_jwt_secret="dev-supabase-jwt-secret",
            razorpay_key_id="dev-razorpay-key-id",
            razorpay_key_secret="dev-razorpay-key-secret",
            razorpay_webhook_secret="dev-razorpay-webhook-secret",
        )


def test_settings_production_accepts_non_dev_secrets() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        supabase_jwt_secret="real-supabase-secret",
        razorpay_key_id="rzp_live_key",
        razorpay_key_secret="real-razorpay-secret",
        razorpay_webhook_secret="real-webhook-secret",
    )

    assert settings.is_production is True
