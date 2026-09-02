"""Gemini settings and factory regression tests."""

from __future__ import annotations

import pytest

from app.ai.factory import create_llm_provider, gemini_api_key_configured
from app.core.config import Settings


def test_default_gemini_model_name() -> None:
    settings = Settings()
    assert settings.gemini_model_name == "gemini-3.6-flash"


def test_gemini_model_name_environment_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_MODEL_NAME", "custom-compatible-model")
    settings = Settings()
    assert settings.gemini_model_name == "custom-compatible-model"


def test_missing_api_key_provider_unavailable() -> None:
    settings = Settings(gemini_api_key=None)
    assert gemini_api_key_configured(settings) is False
    assert create_llm_provider(settings) is None


def test_placeholder_api_key_provider_unavailable() -> None:
    from pydantic import SecretStr

    settings = Settings(gemini_api_key=SecretStr("dev-placeholder-key"))
    assert gemini_api_key_configured(settings) is False
    assert create_llm_provider(settings) is None


def test_real_api_key_creates_provider() -> None:
    from pydantic import SecretStr

    settings = Settings(gemini_api_key=SecretStr("real-secret-key-value"))
    assert gemini_api_key_configured(settings) is True
    provider = create_llm_provider(settings)
    assert provider is not None
    assert provider.model_name == "gemini-3.6-flash"
