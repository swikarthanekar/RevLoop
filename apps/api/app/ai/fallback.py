"""Deterministic template fallbacks for explanation and outreach."""

from __future__ import annotations

from app.ai.formatting import format_probability_percent
from app.ai.schemas import (
    ExplanationInput,
    OutreachDraft,
    OutreachInput,
    OutreachLanguage,
    RecommendationExplanation,
)
from app.domain.enums import RecoveryActionType


def _approval_text(policy_requires_approval: bool) -> str:
    if policy_requires_approval:
        return "Manual approval is required before execution."
    return "No manual approval is required under current policy."


def build_explanation_fallback(input_data: ExplanationInput) -> RecommendationExplanation:
    top_factors = input_data.approved_evidence_statements[:2]
    if not top_factors:
        top_factors = ["Current case evidence supports the selected action."]
    summary = (
        f"Recommended: {input_data.selected_action_label}. "
        f"Estimated recovery probability: "
        f"{format_probability_percent(input_data.success_probability)}."
    )[:240]
    return RecommendationExplanation(
        summary=summary,
        evidence=[top_factors[0], *top_factors[1:3]][:4],
        safety=[_approval_text(input_data.policy.requires_approval)][:3],
        customer_impact="The customer may need a clear next step to complete payment.",
    )


OUTREACH_TEMPLATES: dict[tuple[str, OutreachLanguage], str] = {
    ("CREATE_PAYMENT_LINK", "en"): (
        "Hi {name}, your payment of {amount} did not complete. "
        "Please use this secure link to finish payment: {url}"
    ),
    ("WAIT", "en"): (
        "Hi {name}, your payment of {amount} did not complete. "
        "We will retry shortly and share an update."
    ),
    ("STOP", "en"): (
        "Hi {name}, we have paused further recovery attempts for your payment of {amount}."
    ),
    ("REQUEST_ALTERNATE_PAYMENT_METHOD", "en"): (
        "Hi {name}, your payment of {amount} did not complete. "
        "Please try an alternate payment method when convenient."
    ),
    ("RETRY_SAME_METHOD", "en"): (
        "Hi {name}, your payment of {amount} did not complete. "
        "You may retry the same payment method."
    ),
    ("CREATE_PAYMENT_LINK", "hi"): (
        "Namaste {name}, aapka {amount} payment poora nahi hua. "
        "Kripya is secure link se payment karein: {url}"
    ),
    ("WAIT", "hi"): (
        "Namaste {name}, aapka {amount} payment poora nahi hua. "
        "Hum jald dubara prayas karenge."
    ),
    ("CREATE_PAYMENT_LINK", "hinglish"): (
        "Hi {name}, aapka {amount} payment complete nahi hua. "
        "Please is secure link se pay karein: {url}"
    ),
    ("WAIT", "hinglish"): (
        "Hi {name}, aapka {amount} payment complete nahi hua. "
        "Hum thodi der mein retry karenge."
    ),
}


def build_outreach_fallback(input_data: OutreachInput) -> OutreachDraft:
    template_key = (input_data.approved_action, input_data.language)
    template = OUTREACH_TEMPLATES.get(template_key)
    if template is None:
        template = OUTREACH_TEMPLATES.get((input_data.approved_action, "en"))
    if template is None:
        template = (
            "Hi {name}, your payment of {amount} did not complete. "
            "Please follow the approved recovery step."
        )
    safe_name = input_data.customer_first_name.strip()[:40] or "Customer"
    message = template.format(
        name=safe_name,
        amount=input_data.approved_amount_display,
        url=input_data.payment_link_url or "",
    ).strip()
    cta_text = None
    if input_data.approved_action == RecoveryActionType.CREATE_PAYMENT_LINK.value:
        cta_text = "Pay now"
    return OutreachDraft(
        subject="Payment assistance",
        message=message[:480],
        cta_text=cta_text,
        language=input_data.language,
    )
