"""LLM explanation and outreach services (Prompt 17)."""

from app.ai.explanations import RecommendationExplanationService
from app.ai.outreach import OutreachDraftService
from app.ai.provider import FakeLLMProvider, LLMProvider
from app.ai.schemas import (
    ExplanationResult,
    OutreachDraft,
    OutreachResult,
    RecommendationExplanation,
)

__all__ = [
    "ExplanationResult",
    "FakeLLMProvider",
    "LLMProvider",
    "OutreachDraft",
    "OutreachDraftService",
    "OutreachResult",
    "RecommendationExplanation",
    "RecommendationExplanationService",
]
