"""Pydantic schemas for LLM explanation and outreach (Prompt 17)."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ExplanationSource = Literal["LLM", "TEMPLATE_FALLBACK"]
OutreachLanguage = Literal["en", "hi", "hinglish"]


class EvidenceFactorInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    impact: str


class PolicyInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    eligible: bool
    requires_approval: bool
    reasons: list[str] = Field(default_factory=list)


class ExplanationInput(BaseModel):
    """Approved structured evidence for recommendation explanation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_type: str
    amount_minor: int = Field(ge=0)
    currency: str
    failure_category: str
    selected_action: str
    success_probability: Decimal = Field(ge=0, le=1)
    expected_recovered_minor: int = Field(ge=0)
    expected_value_minor: int
    confidence: Decimal = Field(ge=0, le=1)
    evidence_factors: list[EvidenceFactorInput] = Field(default_factory=list)
    policy: PolicyInput
    approved_evidence_statements: list[str] = Field(default_factory=list)
    approved_numeric_tokens: list[str] = Field(default_factory=list)
    allowed_probability_phrases: list[str] = Field(default_factory=list)
    allowed_money_phrases: list[str] = Field(default_factory=list)
    allowed_confidence_phrases: list[str] = Field(default_factory=list)
    selected_action_label: str


class RecommendationExplanation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    summary: str = Field(max_length=240)
    evidence: list[str] = Field(min_length=1, max_length=4)
    safety: list[str] = Field(default_factory=list, max_length=3)
    customer_impact: str | None = None

    @field_validator("summary")
    @classmethod
    def summary_not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("summary must not be blank")
        return cleaned


class OutreachInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    customer_first_name: str = Field(max_length=80)
    amount_minor: int = Field(ge=0)
    currency: str
    approved_action: str
    payment_link_url: str | None = None
    failure_message_class: str
    tone: Literal["professional"] = "professional"
    language: OutreachLanguage = "en"
    approved_amount_display: str
    approved_action_label: str


class OutreachDraft(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    subject: str | None = Field(default=None, max_length=120)
    message: str = Field(max_length=480)
    cta_text: str | None = Field(default=None, max_length=80)
    language: OutreachLanguage

    @field_validator("message")
    @classmethod
    def message_not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("message must not be blank")
        return cleaned


class ExplanationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    explanation: RecommendationExplanation
    explanation_source: ExplanationSource
    provider_name: str | None = None
    model_name: str | None = None
    failure_category: str | None = None


class OutreachResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    draft: OutreachDraft
    source: ExplanationSource
    provider_name: str | None = None
    model_name: str | None = None
    failure_category: str | None = None
