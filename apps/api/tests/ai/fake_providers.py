"""Fake LLM providers that echo approved input facts."""

from __future__ import annotations

from pydantic import BaseModel

from app.ai.provider import CallableLLMProvider


def build_grounded_explanation_provider():
    async def handler(task: str, input: BaseModel, output_schema: type):
        from app.ai.schemas import ExplanationInput

        assert isinstance(input, ExplanationInput)
        evidence = input.approved_evidence_statements[:1] or [
            "Current case evidence supports the selected action."
        ]
        approval = (
            "Manual approval is required before execution."
            if input.policy.requires_approval
            else "No manual approval is required under current policy."
        )
        return output_schema(
            summary=f"Recommended: {input.selected_action_label}.",
            evidence=evidence,
            safety=[approval],
            customer_impact="The customer receives a clear next step.",
        )

    return CallableLLMProvider(handler)


def build_grounded_outreach_provider(approved_url: str):
    async def handler(task: str, input: BaseModel, output_schema: type):
        from app.ai.schemas import OutreachInput

        assert isinstance(input, OutreachInput)
        if input.payment_link_url:
            message = (
                f"Hi {input.customer_first_name}, your payment of "
                f"{input.approved_amount_display} did not complete. "
                f"Please use this secure link: {approved_url}"
            )
        else:
            message = (
                f"Hi {input.customer_first_name}, your payment of "
                f"{input.approved_amount_display} did not complete."
            )
        return output_schema(
            subject="Payment assistance",
            message=message,
            cta_text="Pay now" if input.payment_link_url else None,
            language=input.language,
        )

    return CallableLLMProvider(handler)
