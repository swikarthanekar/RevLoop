"""Deterministic recovery-action identity helpers (Prompt 16)."""

from __future__ import annotations

import hashlib
import json
from uuid import UUID


def build_action_idempotency_key(
    *,
    case_id: UUID,
    recommendation_id: UUID,
    action_type: str,
) -> str:
    return f"recovery:{case_id}:{recommendation_id}:{action_type}"


def build_payment_link_reference_id(action_id: UUID) -> str:
    """Stable Razorpay reference_id (<= 40 chars) for Prompt 14 correlation."""
    reference = f"rl_{action_id.hex}"
    if len(reference) > 40:
        raise ValueError("payment link reference_id exceeds provider limit")
    return reference


def build_request_fingerprint(*, amount_minor: int, currency: str, reference_id: str) -> str:
    payload = {
        "amount": amount_minor,
        "currency": currency.upper(),
        "reference_id": reference_id,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
