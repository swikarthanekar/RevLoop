"""Fail-closed public projection for audit timeline evidence.

SECURITY MODEL — read before changing anything in this module.

``AuditLog.evidence`` is an open JSONB column. Producers across the codebase
write structured operational context into it, and historical rows may contain
anything that was ever written. The public timeline endpoint must therefore not
serialize stored evidence directly.

The previous implementation was a *denylist*: it returned every key except a
fixed set of known-dangerous names. That cannot protect against a key nobody
anticipated (``customer_email_address``, ``reasoning``, ``raw_response``,
``database_url``, ``mobile``, ``card_number``, ``signature`` …), and it also
recursed into nested dictionaries and kept them, so arbitrary nested structures
crossed the API boundary intact.

This module replaces that with an **allowlist**: only the keys enumerated in
``_PUBLIC_EVIDENCE_FIELDS`` are ever emitted, and each one carries an explicit
value validator. A validator returning ``None`` means *omit the key*, so an
allowlisted key holding an unexpected value fails closed rather than being
coerced.

Invariants that must be preserved:

* never return a key that is not explicitly allowlisted;
* never ``str()``/``json.dumps()``/``repr()`` an unexpected value;
* never copy the input mapping and delete from it;
* never expose an arbitrary nested mapping;
* never mutate the caller's evidence mapping.

This is an API projection only. Stored audit history is never rewritten.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

from app.domain.enums import (
    FailureCategory,
    RecoveryActionType,
    RecoveryCaseStatus,
    RecoveryOutcomeType,
)
from app.workflows.events import RecoveryEvent

# Bounds. Reference identifiers in this system are short; anything longer is a
# payload rather than an identifier.
_MAX_REFERENCE_LENGTH = 160
_MAX_TOKEN_LENGTH = 64
_MAX_LIST_ITEMS = 8
# Case versions are small monotonic counters; the ceiling only guards against a
# corrupted row producing an absurd value.
_MAX_VERSION = 1_000_000

# Reference identifiers: ``pay_ABC123``, ``evt_ABC123``, a UUID, or
# ``payment.failed:pay_123``. Deliberately excludes whitespace, quotes, control
# characters and punctuation used by prose, so an identifier field cannot carry
# a stack trace, a header, or an injected line break.
_REFERENCE_PATTERN = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._:\-]*\Z")

# Enum-shaped tokens produced by backend constants, e.g. ``STALE_WEBHOOK_IGNORED``.
# Operator-authored prose never matches this.
_TOKEN_PATTERN = re.compile(r"\A[A-Z][A-Z0-9_]*\Z")

Validator = Callable[[Any], Any | None]


def _enum_value(*enums: type) -> Validator:
    """Accept only exact members of the given backend enums."""
    allowed = {member.value for enum in enums for member in enum}

    def validate(value: Any) -> Any | None:
        if type(value) is not str:
            return None
        return value if value in allowed else None

    return validate


def _token(value: Any) -> Any | None:
    """Accept a bounded SCREAMING_SNAKE token; reject prose."""
    if type(value) is not str:
        return None
    if not 0 < len(value) <= _MAX_TOKEN_LENGTH:
        return None
    return value if _TOKEN_PATTERN.fullmatch(value) else None


def _reference(value: Any) -> Any | None:
    """Accept a bounded identifier-shaped reference; reject prose and payloads."""
    if type(value) is not str:
        return None
    if not 0 < len(value) <= _MAX_REFERENCE_LENGTH:
        return None
    return value if _REFERENCE_PATTERN.fullmatch(value) else None


def _uuid_string(value: Any) -> Any | None:
    """Accept only a canonical UUID string."""
    if type(value) is not str or len(value) > _MAX_REFERENCE_LENGTH:
        return None
    try:
        UUID(value)
    except (ValueError, AttributeError, TypeError):
        return None
    return value


def _version_int(value: Any) -> Any | None:
    """Accept a real ``int`` in range.

    ``type(value) is not int`` rather than ``isinstance`` because ``bool`` is a
    subclass of ``int`` in Python, and ``True`` must not be published as ``1``.
    """
    if type(value) is not int:
        return None
    return value if 0 <= value <= _MAX_VERSION else None


def _boolean(value: Any) -> Any | None:
    if type(value) is not bool:
        return None
    return value


def _iso_datetime(value: Any) -> Any | None:
    """Accept only a parseable ISO-8601 timestamp string."""
    if type(value) is not str or len(value) > _MAX_REFERENCE_LENGTH:
        return None
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value


def _list_of(item_validator: Validator) -> Validator:
    """Accept a bounded list whose every item independently validates.

    A single invalid item rejects the whole list: emitting a partially filtered
    list would silently misrepresent the audit record.
    """

    def validate(value: Any) -> Any | None:
        if type(value) is not list:
            return None
        if not 0 < len(value) <= _MAX_LIST_ITEMS:
            return None
        validated: list[Any] = []
        for item in value:
            checked = item_validator(item)
            if checked is None:
                return None
            validated.append(checked)
        return validated

    return validate


# ---------------------------------------------------------------------------
# The complete set of evidence keys the public timeline endpoint may emit.
#
# Every entry was derived from an actual backend producer (or, for
# ``provider_event_id``, from the documented response in API_CONTRACTS.md
# section 10). Adding a key here is a security decision: it must have a
# justified operator-facing use and a validator that bounds its value.
# ---------------------------------------------------------------------------
_PUBLIC_EVIDENCE_FIELDS: dict[str, Validator] = {
    # --- state machine transition context (app/workflows/state_machine.py) ---
    "transition_event": _enum_value(RecoveryEvent),
    "previous_status": _enum_value(RecoveryCaseStatus),
    "new_status": _enum_value(RecoveryCaseStatus),
    "previous_version": _version_int,
    "new_version": _version_int,
    "analysis_run_id": _uuid_string,
    "action_id": _uuid_string,
    "scheduled_for": _iso_datetime,
    "rejection_recorded": _boolean,
    # System reasons are SCREAMING_SNAKE constants (STALE_WEBHOOK_IGNORED,
    # RECOVERY_MONEY_MISMATCH, …). The token validator admits those and rejects
    # the operator-authored rejection text that also reaches this key.
    "reason": _token,
    # --- provider event ingest (app/services/provider_events.py) ---
    "case_status": _enum_value(RecoveryCaseStatus),
    "source_event_key": _reference,
    "payment_id": _reference,
    "webhook_event_id": _uuid_string,
    # --- documented in API_CONTRACTS.md section 10 ---
    "provider_event_id": _reference,
    # --- case/analysis context (recovery_case_service, demo factory) ---
    "failure_category": _enum_value(FailureCategory),
    "selected_action": _enum_value(RecoveryActionType),
    "outcome": _enum_value(RecoveryOutcomeType),
    "policy_reasons": _list_of(_token),
    "source": _token,
}

# Keys deliberately NOT published, recorded here so the omission is reviewable:
#
#   metadata     - free-form nested mapping on TransitionContext. Arbitrary
#                  structure must never cross the boundary.
#   approver_id  - internal user UUID. It identifies a person, has no display
#                  value while the API exposes no user identity, and is not
#                  required by any documented screen.
#
# Everything else is omitted by construction: absence from the allowlist is the
# default.


def project_timeline_evidence(evidence: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return the publicly safe projection of stored audit evidence.

    Unknown keys are omitted. Allowlisted keys whose value fails validation are
    omitted. The input mapping is never mutated.
    """
    if not evidence or not isinstance(evidence, Mapping):
        return {}

    projected: dict[str, Any] = {}
    for key, validator in _PUBLIC_EVIDENCE_FIELDS.items():
        if key not in evidence:
            continue
        validated = validator(evidence[key])
        if validated is None:
            continue
        projected[key] = validated
    return projected


def public_evidence_keys() -> frozenset[str]:
    """The allowlisted key names, exposed for tests and documentation."""
    return frozenset(_PUBLIC_EVIDENCE_FIELDS)
