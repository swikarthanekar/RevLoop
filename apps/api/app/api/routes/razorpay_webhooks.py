"""Razorpay webhook HTTP route (Prompt 14)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.deps import get_db
from app.core.errors import AppError
from app.integrations.razorpay.errors import (
    InvalidWebhookSignatureError,
    MalformedWebhookPayloadError,
    MissingWebhookSignatureError,
    RazorpayWebhookError,
    WebhookConfigurationError,
    WebhookCorrelationError,
    WebhookProcessingError,
)
from app.integrations.razorpay.webhooks import verify_webhook_signature
from app.services.provider_events import ProviderEventService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["razorpay-webhooks"])


@router.post("/webhooks/razorpay", status_code=204)
async def razorpay_webhook(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    raw_body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature")
    provider_event_id = request.headers.get("x-razorpay-event-id")

    try:
        verify_webhook_signature(
            raw_body=raw_body,
            received_signature=signature,
            webhook_secret=settings.razorpay_webhook_secret.get_secret_value(),
        )
    except WebhookConfigurationError as exc:
        logger.error("Webhook configuration error")
        raise AppError(
            code="WEBHOOK_CONFIGURATION_ERROR",
            message="Webhook endpoint is not configured.",
            status_code=500,
        ) from exc
    except MissingWebhookSignatureError as exc:
        raise AppError(
            code="MISSING_WEBHOOK_SIGNATURE",
            message=str(exc),
            status_code=401,
        ) from exc
    except InvalidWebhookSignatureError as exc:
        raise AppError(
            code="INVALID_WEBHOOK_SIGNATURE",
            message=str(exc),
            status_code=401,
        ) from exc

    if not provider_event_id:
        raise AppError(
            code="MISSING_WEBHOOK_EVENT_ID",
            message="Missing x-razorpay-event-id header.",
            status_code=400,
        )

    service = ProviderEventService(db, settings=settings)
    try:
        service.ingest_razorpay_webhook(
            raw_body=raw_body,
            provider_event_id=provider_event_id,
            settings=settings,
        )
    except OperationalError as exc:
        db.rollback()
        logger.error("Database unavailable during webhook processing")
        raise AppError(
            code="SERVICE_UNAVAILABLE",
            message="Service temporarily unavailable.",
            status_code=503,
        ) from exc
    except MalformedWebhookPayloadError as exc:
        raise AppError(
            code="MALFORMED_WEBHOOK_PAYLOAD",
            message=str(exc),
            status_code=400,
        ) from exc
    except WebhookCorrelationError as exc:
        logger.warning("Webhook correlation failure: %s", exc)
        raise AppError(
            code="WEBHOOK_CORRELATION_ERROR",
            message="Unable to correlate provider entity.",
            status_code=400,
        ) from exc
    except WebhookProcessingError as exc:
        db.rollback()
        logger.warning("Webhook processing failure: %s", exc)
        raise AppError(
            code="WEBHOOK_PROCESSING_FAILED",
            message="Webhook event could not be processed safely.",
            status_code=500,
        ) from exc
    except RazorpayWebhookError as exc:
        raise AppError(
            code="WEBHOOK_ERROR",
            message=str(exc),
            status_code=400,
        ) from exc
    except Exception as exc:
        db.rollback()
        logger.exception("Webhook processing failed for event %s", provider_event_id)
        raise AppError(
            code="WEBHOOK_PROCESSING_FAILED",
            message="Webhook event could not be processed safely.",
            status_code=500,
        ) from exc

    return Response(status_code=204)
