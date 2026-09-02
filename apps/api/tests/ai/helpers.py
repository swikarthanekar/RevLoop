"""Shared AI test helpers."""

from __future__ import annotations

from decimal import Decimal

from app.ai.schemas import EvidenceFactorInput, ExplanationInput, PolicyInput


def sample_explanation_input(**overrides) -> ExplanationInput:
    base = ExplanationInput(
        case_type="PAYMENT_FAILURE",
        amount_minor=499900,
        currency="INR",
        failure_category="PAYMENT_RAIL_DOWNTIME",
        selected_action="CREATE_PAYMENT_LINK",
        success_probability=Decimal("0.82"),
        expected_recovered_minor=409918,
        expected_value_minor=402500,
        confidence=Decimal("0.87"),
        evidence_factors=[
            EvidenceFactorInput(code="ACTIVE_RAIL_DOWNTIME", impact="HIGH"),
            EvidenceFactorInput(code="RECENT_METHOD_SUCCESS", impact="MEDIUM"),
        ],
        policy=PolicyInput(eligible=True, requires_approval=False, reasons=[]),
        approved_evidence_statements=[
            "The payment rail shows active degradation.",
            "The customer recently succeeded with this payment method.",
        ],
        approved_numeric_tokens=["82%", "87%", "INR 4999.00", "409918", "402500", "499900"],
        allowed_probability_phrases=["82%"],
        allowed_money_phrases=["INR 4999.00", "INR 4099.18"],
        allowed_confidence_phrases=["87%"],
        selected_action_label="Create a payment link",
    )
    return base.model_copy(update=overrides)


def collision_explanation_input(**overrides) -> ExplanationInput:
    """Input where amount display contains 95 but probability is 82%."""
    base = ExplanationInput(
        case_type="PAYMENT_FAILURE",
        amount_minor=9500,
        currency="INR",
        failure_category="PAYMENT_RAIL_DOWNTIME",
        selected_action="CREATE_PAYMENT_LINK",
        success_probability=Decimal("0.82"),
        expected_recovered_minor=8200,
        expected_value_minor=8000,
        confidence=Decimal("0.70"),
        evidence_factors=[
            EvidenceFactorInput(code="ACTIVE_RAIL_DOWNTIME", impact="HIGH"),
        ],
        policy=PolicyInput(eligible=True, requires_approval=False, reasons=[]),
        approved_evidence_statements=[
            "The payment rail shows active degradation.",
        ],
        approved_numeric_tokens=["82%", "70%", "INR 95.00", "8200", "8000", "9500"],
        allowed_probability_phrases=["82%"],
        allowed_money_phrases=["INR 95.00", "INR 82.00"],
        allowed_confidence_phrases=["70%"],
        selected_action_label="Create a payment link",
    )
    return base.model_copy(update=overrides)
