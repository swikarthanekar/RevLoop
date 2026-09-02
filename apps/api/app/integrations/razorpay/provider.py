"""Razorpay read-client composition for recovery analysis (Prompt 15)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import httpx

from app.core.config import Settings
from app.integrations.razorpay.client import RazorpayClient
from app.integrations.razorpay.errors import RazorpayConfigurationError

RazorpayClientFactory = Callable[[Settings], RazorpayClient]


def is_razorpay_api_configured(settings: Settings) -> bool:
    """Return True when non-blank, non-dev placeholder API credentials are present."""
    key_id = settings.razorpay_key_id.get_secret_value()
    key_secret = settings.razorpay_key_secret.get_secret_value()
    if not key_id or not key_id.strip():
        return False
    if not key_secret or not key_secret.strip():
        return False
    if key_id.strip().startswith("dev-"):
        return False
    if key_secret.strip().startswith("dev-"):
        return False
    return True


def create_razorpay_read_client(
    settings: Settings,
    *,
    transport: httpx.BaseTransport | None = None,
) -> RazorpayClient:
    """Build a read-only Razorpay client; raises RazorpayConfigurationError when invalid."""
    return RazorpayClient.from_settings(settings, transport=transport)


@dataclass(frozen=True)
class RazorpayReadClientHandle:
    client: RazorpayClient
    owned: bool


def acquire_razorpay_read_client(
    settings: Settings,
    *,
    injected: RazorpayClient | None = None,
    factory: RazorpayClientFactory | None = None,
) -> RazorpayReadClientHandle | None:
    """Return a client handle for downtime reads, or None when credentials are unavailable."""
    if injected is not None:
        return RazorpayReadClientHandle(client=injected, owned=False)
    if not is_razorpay_api_configured(settings):
        return None
    build = factory or create_razorpay_read_client
    try:
        return RazorpayReadClientHandle(client=build(settings), owned=True)
    except RazorpayConfigurationError:
        return None
