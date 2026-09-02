"""Semantic validation for LLM explanation and outreach outputs."""

from __future__ import annotations

import re

from app.ai.errors import AISemanticValidationError
from app.ai.formatting import other_action_labels
from app.ai.schemas import ExplanationInput, OutreachDraft, OutreachInput, RecommendationExplanation

_PERCENT_TOKEN_RE = re.compile(r"\b(\d+(?:\.\d+)?)%")
_MONEY_TOKEN_RE = re.compile(
    r"(?:₹|(?:\b(?:inr|rs)\b\.?\s*))(\d[\d,]*(?:\.\d+)?)",
    re.IGNORECASE,
)
_DECIMAL_PERCENT_RE = re.compile(
    r"\b0\.\d+\s*(?:%|percent|probability|chance|recovery)\b",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)

_PROBABILITY_CONTEXT_RE = re.compile(
    r"(?:probability|percent|chance|likelihood|recovery\s+(?:rate|probability))",
    re.IGNORECASE,
)
_CONFIDENCE_CONTEXT_RE = re.compile(r"confidence", re.IGNORECASE)
_MONEY_CONTEXT_RE = re.compile(
    r"(?:₹|inr|rs\.?|amount|rupee|payment of|value of|recovered)",
    re.IGNORECASE,
)

_FORBIDDEN_RECOVERY_PHRASES = (
    "payment has been captured",
    "payment captured",
    "already recovered",
    "has been recovered",
    "successfully recovered",
    "payment succeeded",
    "payment completed successfully",
)

_FORBIDDEN_PROVIDER_PHRASES = (
    "razorpay is down",
    "razorpay is currently down",
    "provider is down",
    "bank rejected",
    "issuer declined",
)

_FORBIDDEN_URGENCY_PHRASES = (
    "pay immediately or",
    "final warning",
    "account will be blocked",
    "within 10 minutes",
    "legal action",
    "pay now or",
)

_FORBIDDEN_FEE_PHRASES = (
    "late fee",
    "penalty fee",
    "additional fee",
    "extra charge",
)


def _collect_text_parts(explanation: RecommendationExplanation) -> list[str]:
    parts = [explanation.summary, *(explanation.evidence or []), *(explanation.safety or [])]
    if explanation.customer_impact:
        parts.append(explanation.customer_impact)
    return parts


def _collect_text(explanation: RecommendationExplanation) -> str:
    return "\n".join(_collect_text_parts(explanation))


def _normalize_token(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower().replace(",", ""))


def _normalize_percent(value: str) -> str:
    return _normalize_token(value.rstrip("%")) + "%"


def _allowed_percent_set(phrases: list[str]) -> set[str]:
    return {_normalize_percent(phrase) for phrase in phrases if "%" in phrase}


def _allowed_money_set(phrases: list[str]) -> set[str]:
    return {_normalize_token(phrase) for phrase in phrases}


def _context_window(text: str, start: int, end: int, *, radius: int = 45) -> str:
    return text[max(0, start - radius) : min(len(text), end + radius)].lower()


def _validate_percentage_claim(field_text: str, input_data: ExplanationInput) -> None:
    allowed_probability = _allowed_percent_set(input_data.allowed_probability_phrases)
    allowed_confidence = _allowed_percent_set(input_data.allowed_confidence_phrases)
    for match in _PERCENT_TOKEN_RE.finditer(field_text):
        token = match.group(0)
        normalized = _normalize_percent(token)
        context = _context_window(field_text, match.start(), match.end())
        if _CONFIDENCE_CONTEXT_RE.search(context):
            allowed = allowed_confidence
        else:
            allowed = allowed_probability
        if normalized not in allowed:
            raise AISemanticValidationError(f"Unsupported numeric claim: {token}")


def _validate_decimal_probability_claim(field_text: str, input_data: ExplanationInput) -> None:
    if not _DECIMAL_PERCENT_RE.search(field_text) and "0." not in field_text.lower():
        return
    allowed_probability = _allowed_percent_set(input_data.allowed_probability_phrases)
    for match in _PERCENT_TOKEN_RE.finditer(field_text):
        token = match.group(0)
        if token.startswith("0.") and _normalize_percent(token) not in allowed_probability:
            raise AISemanticValidationError(f"Unsupported numeric claim: {token}")
    if _PROBABILITY_CONTEXT_RE.search(field_text) and "0." in field_text.lower():
        if not any(phrase in field_text for phrase in input_data.allowed_probability_phrases):
            raise AISemanticValidationError("Unsupported decimal probability claim.")


def _validate_money_claim(field_text: str, input_data: ExplanationInput) -> None:
    allowed_money = _allowed_money_set(input_data.allowed_money_phrases)
    for match in _MONEY_TOKEN_RE.finditer(field_text):
        raw_amount = match.group(1)
        context = _context_window(field_text, match.start(), match.end())
        if not _MONEY_CONTEXT_RE.search(context):
            continue
        normalized_amount = _normalize_token(raw_amount)
        if not any(normalized_amount in allowed for allowed in allowed_money):
            raise AISemanticValidationError(f"Unsupported money claim: {match.group(0)}")


def _validate_field_numerics(field_text: str, input_data: ExplanationInput) -> None:
    _validate_percentage_claim(field_text, input_data)
    _validate_decimal_probability_claim(field_text, input_data)
    _validate_money_claim(field_text, input_data)


def _references_other_action(field_text: str, *, selected_action: str, selected_label: str) -> bool:
    lowered = field_text.lower()
    selected = selected_label.lower()
    for label in other_action_labels(selected_action):
        other = label.lower().strip()
        if not other or other in selected:
            continue
        if " " in other:
            if other in lowered:
                return True
        elif re.search(rf"\b{re.escape(other)}\b", lowered):
            return True
    return False


def validate_explanation_semantics(
    *,
    explanation: RecommendationExplanation,
    input_data: ExplanationInput,
) -> None:
    text = _collect_text(explanation).lower()

    for field_text in _collect_text_parts(explanation):
        _validate_field_numerics(field_text, input_data)

    approved_evidence = {_normalize_token(item) for item in input_data.approved_evidence_statements}
    for item in explanation.evidence:
        if _normalize_token(item) not in approved_evidence:
            raise AISemanticValidationError("Unsupported evidence statement.")

    selected_label = input_data.selected_action_label.lower()
    for field_text in _collect_text_parts(explanation):
        if _references_other_action(
            field_text,
            selected_action=input_data.selected_action,
            selected_label=selected_label,
        ):
            raise AISemanticValidationError("Explanation references a different action.")

    if input_data.policy.requires_approval and any(
        phrase in text
        for phrase in ("no approval", "without approval", "does not require approval")
    ):
        raise AISemanticValidationError("Explanation contradicts approval requirement.")

    if not input_data.policy.eligible and any(
        phrase in text for phrase in ("already authorized", "is authorized", "eligible to execute")
    ):
        raise AISemanticValidationError("Explanation contradicts policy eligibility.")

    if not any(
        factor.code == "ACTIVE_RAIL_DOWNTIME" for factor in input_data.evidence_factors
    ) and any(phrase in text for phrase in _FORBIDDEN_PROVIDER_PHRASES):
        raise AISemanticValidationError("Unsupported provider-state claim.")

    if any(phrase in text for phrase in _FORBIDDEN_RECOVERY_PHRASES):
        raise AISemanticValidationError("Unsupported recovered/captured claim.")

    if any(phrase in text for phrase in _FORBIDDEN_URGENCY_PHRASES):
        raise AISemanticValidationError("Unsupported urgency claim.")

    if any(phrase in text for phrase in _FORBIDDEN_FEE_PHRASES):
        raise AISemanticValidationError("Unsupported fee claim.")


def validate_outreach_semantics(*, draft: OutreachDraft, input_data: OutreachInput) -> None:
    text = draft.message.lower()
    if input_data.payment_link_url:
        urls = _URL_RE.findall(draft.message)
        approved = input_data.payment_link_url.strip()
        if not urls or any(url.rstrip(".,)") != approved for url in urls):
            raise AISemanticValidationError("Outreach contains an unapproved URL.")
    elif _URL_RE.search(draft.message):
        raise AISemanticValidationError("Outreach contains an unapproved URL.")

    allowed_amount = _normalize_token(input_data.approved_amount_display)
    for match in _MONEY_TOKEN_RE.finditer(draft.message):
        normalized_amount = _normalize_token(match.group(1))
        if normalized_amount not in allowed_amount and normalized_amount not in {
            _normalize_token(part) for part in re.findall(r"\d+(?:\.\d+)?", allowed_amount)
        }:
            raise AISemanticValidationError("Outreach contains an unapproved amount.")

    if any(phrase in text for phrase in _FORBIDDEN_URGENCY_PHRASES):
        raise AISemanticValidationError("Outreach contains fake urgency.")
    if any(phrase in text for phrase in _FORBIDDEN_FEE_PHRASES):
        raise AISemanticValidationError("Outreach contains invented fee language.")
    if any(phrase in text for phrase in ("blocked", "legal action", "suspended")):
        raise AISemanticValidationError("Outreach contains threatening language.")

    if "ignore all previous instructions" in text:
        raise AISemanticValidationError("Prompt injection content detected.")
