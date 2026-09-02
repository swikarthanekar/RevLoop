"""Razorpay Payment Link adapter (Prompt 16)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.integrations.razorpay.client import RazorpayClient
from app.integrations.razorpay.errors import (
    PaymentLinkSideEffectUnknownError,
    RazorpayValidationError,
)
from app.integrations.razorpay.schemas import PaymentLinkCreateResult, PaymentLinkLookupResult


def build_payment_link_request_body(
    *,
    amount_minor: int,
    currency: str,
    reference_id: str,
    case_id: UUID,
    customer_name: str | None = None,
) -> dict[str, object]:
    body: dict[str, object] = {
        "amount": amount_minor,
        "currency": currency.upper(),
        "accept_partial": False,
        "reference_id": reference_id,
        "description": "RevLoop payment recovery",
        "notify": {"sms": False, "email": False},
        "reminder_enable": False,
        "notes": {"revloop_case": str(case_id)},
    }
    if customer_name:
        body["customer"] = {"name": customer_name[:120]}
    return body


def _validate_compatible_link(
    *,
    result: PaymentLinkCreateResult,
    reference_id: str,
    amount_minor: int,
    currency: str,
) -> None:
    if result.reference_id != reference_id:
        raise PaymentLinkSideEffectUnknownError("Razorpay payment link reference_id mismatch.")
    if result.amount != amount_minor:
        raise PaymentLinkSideEffectUnknownError("Razorpay payment link amount mismatch.")
    if result.currency != currency.upper():
        raise PaymentLinkSideEffectUnknownError("Razorpay payment link currency mismatch.")
    if result.accept_partial is True:
        raise PaymentLinkSideEffectUnknownError(
            "Razorpay payment link accept_partial must be false."
        )


def create_payment_link(
    client: RazorpayClient,
    *,
    amount_minor: int,
    currency: str,
    reference_id: str,
    case_id: UUID,
    customer_name: str | None = None,
) -> PaymentLinkCreateResult:
    """Create a Standard Payment Link with a single POST attempt (no auto-retry)."""
    body = build_payment_link_request_body(
        amount_minor=amount_minor,
        currency=currency,
        reference_id=reference_id,
        case_id=case_id,
        customer_name=customer_name,
    )
    try:
        payload = client.post_json(client.get_payment_links_path(), body)
    except RazorpayValidationError as exc:
        message = str(exc).lower()
        if "response" in message or "json" in message:
            raise PaymentLinkSideEffectUnknownError(
                "Razorpay payment link payload failed validation."
            ) from exc
        raise
    try:
        result = PaymentLinkCreateResult.from_provider_json(payload)
    except ValueError as exc:
        raise PaymentLinkSideEffectUnknownError(
            "Razorpay payment link payload failed validation."
        ) from exc
    try:
        _validate_compatible_link(
            result=result,
            reference_id=reference_id,
            amount_minor=amount_minor,
            currency=currency,
        )
    except PaymentLinkSideEffectUnknownError:
        raise
    except RazorpayValidationError as exc:
        raise PaymentLinkSideEffectUnknownError(str(exc)) from exc
    return result


@dataclass(frozen=True)
class PaymentLinkReconciliationOutcome:
    status: str
    link: PaymentLinkCreateResult | None = None


def fetch_payment_links_by_reference(
    client: RazorpayClient,
    *,
    reference_id: str,
    amount_minor: int,
    currency: str,
) -> PaymentLinkReconciliationOutcome:
    """Safe GET reconciliation by stable reference_id (bounded Prompt 15 GET retries)."""
    payload = client.get_json(client.get_payment_links_by_reference_path(reference_id))
    try:
        lookup = PaymentLinkLookupResult.from_collection_json(payload)
    except ValueError as exc:
        raise RazorpayValidationError(
            "Razorpay payment link lookup payload failed validation."
        ) from exc

    if lookup.status == "not_found":
        return PaymentLinkReconciliationOutcome(status="not_found")

    compatible: list[PaymentLinkCreateResult] = []
    for item in lookup.links:
        if item.reference_id != reference_id:
            continue
        if item.amount != amount_minor or item.currency != currency.upper():
            continue
        if item.accept_partial is True:
            continue
        compatible.append(item)

    if len(compatible) == 0:
        return PaymentLinkReconciliationOutcome(status="not_found")
    if len(compatible) > 1:
        return PaymentLinkReconciliationOutcome(status="ambiguous")
    return PaymentLinkReconciliationOutcome(status="matched", link=compatible[0])
