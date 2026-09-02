"""Razorpay provider composition tests (Prompt 15 hardening)."""

from __future__ import annotations

from pydantic import SecretStr

from app.core.config import Settings
from app.integrations.razorpay.provider import is_razorpay_api_configured


def test_dev_placeholder_credentials_are_not_configured() -> None:
    settings = Settings(
        razorpay_key_id=SecretStr("dev-razorpay-key-id"),
        razorpay_key_secret=SecretStr("dev-razorpay-key-secret"),
    )
    assert is_razorpay_api_configured(settings) is False


def test_blank_credentials_are_not_configured() -> None:
    settings = Settings(
        razorpay_key_id=SecretStr(""),
        razorpay_key_secret=SecretStr(""),
    )
    assert is_razorpay_api_configured(settings) is False


def test_non_dev_credentials_are_configured() -> None:
    settings = Settings(
        razorpay_key_id=SecretStr("rzp_test_key"),
        razorpay_key_secret=SecretStr("secret"),
    )
    assert is_razorpay_api_configured(settings) is True
