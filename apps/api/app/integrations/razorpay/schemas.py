"""Narrow Razorpay webhook payload schemas (Prompt 14)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def unix_to_utc(value: int | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc)


class RazorpayPaymentEntity(BaseModel):
    id: str
    amount: int
    currency: str
    status: str
    method: str | None = None
    order_id: str | None = None
    email: str | None = None
    contact: str | None = None
    error_code: str | None = None
    error_reason: str | None = None
    error_source: str | None = None
    error_step: str | None = None
    error_description: str | None = None
    created_at: int | None = None
    notes: dict[str, Any] = Field(default_factory=dict)

    @property
    def provider_created_at(self) -> datetime | None:
        return unix_to_utc(self.created_at)


class RazorpaySubscriptionEntity(BaseModel):
    id: str
    status: str
    plan_id: str | None = None
    current_start: int | None = None
    current_end: int | None = None
    charge_at: int | None = None
    created_at: int | None = None
    notes: dict[str, Any] = Field(default_factory=dict)

    @property
    def provider_created_at(self) -> datetime | None:
        return unix_to_utc(self.created_at)


class RazorpayPaymentLinkEntity(BaseModel):
    id: str
    amount: int
    currency: str
    status: str
    reference_id: str | None = None
    payments: list[dict[str, Any]] = Field(default_factory=list)
    notes: dict[str, Any] = Field(default_factory=dict)
    created_at: int | None = None

    @property
    def provider_created_at(self) -> datetime | None:
        return unix_to_utc(self.created_at)


class RazorpayWebhookEnvelope(BaseModel):
    event: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: int | None = None

    @property
    def provider_created_at(self) -> datetime | None:
        return unix_to_utc(self.created_at)

    def payment_entity(self) -> RazorpayPaymentEntity | None:
        payment = self.payload.get("payment")
        if not isinstance(payment, dict):
            return None
        entity = payment.get("entity")
        if not isinstance(entity, dict):
            return None
        return RazorpayPaymentEntity.model_validate(entity)

    def subscription_entity(self) -> RazorpaySubscriptionEntity | None:
        subscription = self.payload.get("subscription")
        if not isinstance(subscription, dict):
            return None
        entity = subscription.get("entity")
        if not isinstance(entity, dict):
            return None
        return RazorpaySubscriptionEntity.model_validate(entity)

    def payment_link_entity(self) -> RazorpayPaymentLinkEntity | None:
        payment_link = self.payload.get("payment_link")
        if not isinstance(payment_link, dict):
            return None
        entity = payment_link.get("entity")
        if not isinstance(entity, dict):
            return None
        return RazorpayPaymentLinkEntity.model_validate(entity)


# --- Prompt 15: HTTP API read DTOs ---


class RazorpayPaymentRead(BaseModel):
    """Narrow payment evidence from GET /v1/payments/:id."""

    id: str
    status: str
    amount: int
    currency: str
    method: str | None = None
    order_id: str | None = None
    error_code: str | None = None
    error_reason: str | None = None
    error_source: str | None = None
    error_step: str | None = None
    error_description: str | None = None
    provider_created_at: datetime | None = None
    captured: bool | None = None

    @classmethod
    def from_provider_json(cls, payload: dict[str, Any]) -> RazorpayPaymentRead:
        if not isinstance(payload.get("id"), str) or not payload["id"].strip():
            raise ValueError("payment id is required")
        amount = payload.get("amount")
        if not isinstance(amount, int):
            raise ValueError("payment amount must be integer minor units")
        currency = payload.get("currency")
        if not isinstance(currency, str) or not currency.strip():
            raise ValueError("payment currency is required")
        status = payload.get("status")
        if not isinstance(status, str) or not status.strip():
            raise ValueError("payment status is required")
        return cls(
            id=payload["id"],
            status=status,
            amount=amount,
            currency=currency.strip().upper(),
            method=payload.get("method") if isinstance(payload.get("method"), str) else None,
            order_id=payload.get("order_id") if isinstance(payload.get("order_id"), str) else None,
            error_code=payload.get("error_code")
            if isinstance(payload.get("error_code"), str)
            else None,
            error_reason=payload.get("error_reason")
            if isinstance(payload.get("error_reason"), str)
            else None,
            error_source=payload.get("error_source")
            if isinstance(payload.get("error_source"), str)
            else None,
            error_step=payload.get("error_step")
            if isinstance(payload.get("error_step"), str)
            else None,
            error_description=payload.get("error_description")
            if isinstance(payload.get("error_description"), str)
            else None,
            provider_created_at=unix_to_utc(payload.get("created_at"))
            if isinstance(payload.get("created_at"), int)
            else None,
            captured=payload.get("captured") if isinstance(payload.get("captured"), bool) else None,
        )


class PaymentDowntime(BaseModel):
    """Normalized Razorpay payment downtime record."""

    id: str
    method: str
    status: str
    severity: str | None = None
    scheduled: bool = False
    begin_at: datetime | None = None
    end_at: datetime | None = None
    instrument: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def from_provider_json(cls, payload: dict[str, Any]) -> PaymentDowntime:
        downtime_id = payload.get("id")
        if not isinstance(downtime_id, str) or not downtime_id.strip():
            raise ValueError("downtime id is required")
        method = payload.get("method")
        if not isinstance(method, str) or not method.strip():
            raise ValueError("downtime method is required")
        status = payload.get("status")
        if not isinstance(status, str) or not status.strip():
            raise ValueError("downtime status is required")

        instrument_raw = payload.get("instrument")
        instrument: dict[str, str] = {}
        if isinstance(instrument_raw, dict):
            for key, value in instrument_raw.items():
                if isinstance(key, str) and isinstance(value, str):
                    instrument[key] = value

        begin_at = None
        end_at = None
        for begin_key in ("begin", "begin_at"):
            if begin_key not in payload:
                continue
            raw_begin = payload.get(begin_key)
            if raw_begin is None:
                break
            if not isinstance(raw_begin, int):
                raise ValueError(f"{begin_key} must be unix timestamp")
            begin_at = unix_to_utc(raw_begin)
            break
        for end_key in ("end", "end_at"):
            if end_key not in payload:
                continue
            raw_end = payload.get(end_key)
            if raw_end is None:
                break
            if not isinstance(raw_end, int):
                raise ValueError(f"{end_key} must be unix timestamp")
            end_at = unix_to_utc(raw_end)
            break

        severity = payload.get("severity")
        scheduled = payload.get("scheduled")
        return cls(
            id=downtime_id,
            method=method.strip().lower(),
            status=status.strip().lower(),
            severity=severity.strip().lower()
            if isinstance(severity, str) and severity.strip()
            else None,
            scheduled=bool(scheduled) if isinstance(scheduled, bool) else False,
            begin_at=begin_at,
            end_at=end_at,
            instrument=instrument,
        )