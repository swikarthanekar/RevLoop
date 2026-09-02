"""Razorpay payment downtime read + matching (Prompt 15)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from app.integrations.razorpay.client import RazorpayClient
from app.integrations.razorpay.errors import RazorpayValidationError
from app.integrations.razorpay.schemas import PaymentDowntime
from app.recovery.schemas import DowntimeContext, DowntimeSeverity

# Exact Razorpay downtime status tokens (see RAZORPAY_INTEGRATION.md §12).
ACTIVE_DOWNTIME_STATUSES = frozenset({"started", "updated"})
RESOLVED_DOWNTIME_STATUSES = frozenset({"resolved"})
SCHEDULED_DOWNTIME_STATUSES = frozenset({"scheduled"})
SEVERITY_ORDER = {"high": 3, "medium": 2, "low": 1}

MatchResult = Literal["MATCH", "NO_MATCH", "UNCERTAIN"]


def _normalize_method(method: str | None) -> str | None:
    if method is None:
        return None
    normalized = method.strip().lower()
    return normalized or None


def _normalize_severity(severity: str | None) -> DowntimeSeverity:
    if severity in {"high", "medium", "low"}:
        return severity
    if severity is None:
        return "medium"
    return "unknown"


def _parse_downtime_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    payment_downtime = payload.get("payment_downtime")
    if not isinstance(payment_downtime, dict):
        raise ValueError("downtime response missing payment_downtime object")
    items = payment_downtime.get("items")
    if not isinstance(items, list):
        raise ValueError("downtime collection missing items")
    return [item for item in items if isinstance(item, dict)]


def fetch_downtimes(client: RazorpayClient) -> list[PaymentDowntime]:
    """Fetch all payment downtimes; raises typed errors on provider failure."""
    payload = client.get_json(client.get_downtimes_path())
    try:
        raw_items = _parse_downtime_items(payload)
        return [PaymentDowntime.from_provider_json(item) for item in raw_items]
    except ValueError as exc:
        raise RazorpayValidationError("Razorpay downtime payload failed validation.") from exc


def fetch_downtime_by_id(client: RazorpayClient, downtime_id: str) -> PaymentDowntime:
    payload = client.get_json(client.get_downtime_path(downtime_id))
    try:
        return PaymentDowntime.from_provider_json(payload)
    except ValueError as exc:
        raise RazorpayValidationError("Razorpay downtime payload failed validation.") from exc


def _time_window_applies(
    downtime: PaymentDowntime,
    failure_at: datetime | None,
) -> bool | None:
    """Return True if inside window, False if outside, None if failure time is unknown."""
    if failure_at is None:
        return None
    if downtime.begin_at is not None and failure_at < downtime.begin_at:
        return False
    if downtime.end_at is not None and failure_at > downtime.end_at:
        return False
    return True


def _instrument_match(
    downtime: PaymentDowntime,
    instrument: dict[str, str] | None,
) -> MatchResult:
    if not downtime.instrument:
        return "MATCH"
    if not instrument:
        return "UNCERTAIN"
    for key, required in downtime.instrument.items():
        if not required:
            continue
        actual = instrument.get(key)
        if actual is None:
            return "UNCERTAIN"
        if actual.strip().lower() != required.strip().lower():
            return "NO_MATCH"
    return "MATCH"


def evaluate_downtime_match(
    downtime: PaymentDowntime,
    *,
    payment_method: str | None,
    failure_at: datetime | None,
    instrument: dict[str, str] | None,
) -> MatchResult:
    """Return MATCH, NO_MATCH, or UNCERTAIN for one downtime record."""
    normalized_method = _normalize_method(payment_method)
    if normalized_method is None:
        return "UNCERTAIN"

    if downtime.method != normalized_method:
        return "NO_MATCH"

    status = downtime.status.lower()

    if status in RESOLVED_DOWNTIME_STATUSES:
        return "NO_MATCH"

    if status in SCHEDULED_DOWNTIME_STATUSES:
        return "NO_MATCH"

    window = _time_window_applies(downtime, failure_at)
    if window is False:
        return "NO_MATCH"

    if downtime.scheduled and downtime.begin_at is not None and failure_at is not None:
        if failure_at < downtime.begin_at:
            return "NO_MATCH"

    instrument_result = _instrument_match(downtime, instrument)
    if instrument_result == "NO_MATCH":
        return "NO_MATCH"
    if instrument_result == "UNCERTAIN":
        return "UNCERTAIN"

    if status in ACTIVE_DOWNTIME_STATUSES:
        return "MATCH"

    # Relevant record with unrecognized status — cannot prove NO_DOWNTIME.
    return "UNCERTAIN"


def _select_best_match(matches: list[PaymentDowntime]) -> PaymentDowntime:
    return sorted(
        matches,
        key=lambda item: (
            -SEVERITY_ORDER.get(item.severity or "", 0),
            item.id,
        ),
    )[0]


def build_downtime_context_from_records(
    records: list[PaymentDowntime],
    *,
    payment_method: str | None,
    failure_at: datetime | None,
    instrument: dict[str, str] | None,
) -> DowntimeContext:
    if not records:
        return DowntimeContext(
            lookup_status="NO_DOWNTIME",
            rail_degraded=False,
            severity="none",
        )

    matches: list[PaymentDowntime] = []
    uncertain = False
    for record in records:
        result = evaluate_downtime_match(
            record,
            payment_method=payment_method,
            failure_at=failure_at,
            instrument=instrument,
        )
        if result == "MATCH":
            matches.append(record)
        elif result == "UNCERTAIN":
            uncertain = True

    if matches:
        best = _select_best_match(matches)
        return DowntimeContext(
            lookup_status="KNOWN",
            rail_degraded=True,
            severity=_normalize_severity(best.severity),
            matched_method=best.method,
        )

    if uncertain:
        return DowntimeContext(
            lookup_status="UNKNOWN",
            rail_degraded=False,
            severity="unknown",
        )

    return DowntimeContext(
        lookup_status="NO_DOWNTIME",
        rail_degraded=False,
        severity="none",
    )
