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
