"""Outreach draft generation service (Prompt 17)."""

from __future__ import annotations

import asyncio
import logging
import re

from pydantic import ValidationError

from app.ai.errors import AIProviderError
from app.ai.factory import create_llm_provider
from app.ai.fallback import build_outreach_fallback
from app.ai.formatting import action_label, format_minor_amount
from app.ai.provider import LLMProvider
from app.ai.schemas import OutreachDraft, OutreachInput, OutreachResult
from app.ai.validation import validate_outreach_semantics
from app.core.config import Settings
from app.domain.enums import RecoveryActionType

logger = logging.getLogger(__name__)

OUTREACH_TASK = "outreach_draft"
_NAME_SANITIZE_RE = re.compile(r"[\r\n\t]+")


class OutreachDraftService:
    def __init__(
        self,
        *,
        settings: Settings,
        llm_provider: LLMProvider | None = None,
    ) -> None:
        self._settings = settings
        self._llm_provider = llm_provider

    def generate(self, input_data: OutreachInput) -> OutreachResult:
        if (
            input_data.approved_action == RecoveryActionType.CREATE_PAYMENT_LINK.value
            and not input_data.payment_link_url
        ):
            raise ValueError("Payment link outreach requires an approved payment_link_url.")

        provider = self._llm_provider if self._llm_provider is not None else create_llm_provider(
            self._settings
        )
        if provider is None:
            draft = build_outreach_fallback(input_data)
            validate_outreach_semantics(draft=draft, input_data=input_data)
            return OutreachResult(
                draft=draft,
                source="TEMPLATE_FALLBACK",
                failure_category="unavailable",
            )
        try:
            draft = asyncio.run(
                self._generate_with_provider(provider=provider, input_data=input_data)
            )
            return OutreachResult(
                draft=draft,
                source="LLM",
                provider_name=getattr(provider, "provider_name", "llm"),
                model_name=getattr(provider, "model_name", None),
            )
        except AIProviderError as exc:
            logger.info("Outreach fallback category=%s", exc.category)
            draft = build_outreach_fallback(input_data)
            validate_outreach_semantics(draft=draft, input_data=input_data)
            return OutreachResult(
                draft=draft,
                source="TEMPLATE_FALLBACK",
                provider_name=getattr(provider, "provider_name", None),
                model_name=getattr(provider, "model_name", None),
                failure_category=exc.category,
            )

    async def _generate_with_provider(
        self,
        *,
        provider: LLMProvider,
        input_data: OutreachInput,
    ) -> OutreachDraft:
        candidate = await provider.generate_structured(
            task=OUTREACH_TASK,
            input=input_data,
            output_schema=OutreachDraft,
        )
        try:
            validated = OutreachDraft.model_validate(candidate.model_dump())
        except ValidationError as exc:
            raise AIProviderError("Outreach schema validation failed.") from exc
        validate_outreach_semantics(draft=validated, input_data=input_data)
        return validated


def build_outreach_input(
    *,
    customer_first_name: str,
    amount_minor: int,
    currency: str,
    approved_action: str,
    failure_message_class: str,
    payment_link_url: str | None = None,
    language: str = "en",
) -> OutreachInput:
    safe_name = _NAME_SANITIZE_RE.sub(" ", customer_first_name).strip()[:80]
    return OutreachInput(
        customer_first_name=safe_name or "Customer",
        amount_minor=amount_minor,
        currency=currency,
        approved_action=approved_action,
        payment_link_url=payment_link_url,
        failure_message_class=failure_message_class,
        language=language,  # type: ignore[arg-type]
        approved_amount_display=format_minor_amount(amount_minor, currency),
        approved_action_label=action_label(approved_action),
    )
