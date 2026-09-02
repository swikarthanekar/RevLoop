"""Recovery downtime context resolution using Razorpay reads (Prompt 15)."""

from __future__ import annotations

import logging
from datetime import datetime

from app.integrations.razorpay.client import RazorpayClient
from app.integrations.razorpay.downtime import (
    build_downtime_context_from_records,
    fetch_downtimes,
)
from app.integrations.razorpay.errors import RazorpayApiError
from app.models.transaction import Transaction
from app.recovery.schemas import DowntimeContext

logger = logging.getLogger(__name__)

_UNKNOWN = DowntimeContext(
    lookup_status="UNKNOWN",
    rail_degraded=False,
    severity="unknown",
)


def _extract_instrument(transaction: Transaction) -> dict[str, str] | None:
    metadata = transaction.metadata_ or {}
    instrument_raw = metadata.get("instrument")
    if isinstance(instrument_raw, dict):
        instrument: dict[str, str] = {}
        for key, value in instrument_raw.items():
            if isinstance(key, str) and isinstance(value, str):
                instrument[key] = value
        return instrument or None
    return None


def _failure_timestamp(transaction: Transaction) -> datetime | None:
    return transaction.last_provider_event_at or transaction.provider_created_at


def resolve_downtime_context_for_transaction(
    client: RazorpayClient,
    transaction: Transaction,
) -> DowntimeContext:
    """Lookup provider downtime and map to internal recovery context."""
    try:
        records = fetch_downtimes(client)
    except RazorpayApiError as exc:
        logger.warning("Razorpay downtime lookup failed: %s", type(exc).__name__)
        return _UNKNOWN

    return build_downtime_context_from_records(
        records,
        payment_method=transaction.payment_method,
        failure_at=_failure_timestamp(transaction),
        instrument=_extract_instrument(transaction),
    )


def resolve_downtime_context(
    client: RazorpayClient | None,
    transaction: Transaction | None,
    *,
    lookup_configured: bool,
) -> DowntimeContext:
    if transaction is None:
        return DowntimeContext()

    if not lookup_configured or client is None:
        return _UNKNOWN

    return resolve_downtime_context_for_transaction(client, transaction)
