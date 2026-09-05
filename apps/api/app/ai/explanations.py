"""Recommendation explanation enrichment service."""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.errors import AIProviderError
from app.ai.factor_registry import approved_statements_for_factors
from app.ai.factory import create_llm_provider
from app.ai.fallback import build_explanation_fallback
from app.ai.formatting import (
    action_label,
    format_confidence_percent,
    format_minor_amount,
    format_probability_percent,
)
from app.ai.provider import LLMProvider
from app.ai.schemas import (
    EvidenceFactorInput,
    ExplanationInput,
    ExplanationResult,
    PolicyInput,
    RecommendationExplanation,
)
from app.ai.validation import validate_explanation_semantics
from app.core.config import Settings
from app.models.recovery_case import RecoveryCase
from app.models.recovery_recommendation import RecoveryRecommendation
from app.recovery.selection import select_candidate_row, top_ranked_row

logger = logging.getLogger(__name__)

EXPLANATION_TASK = "recommendation_explanation"


class RecommendationExplanationService:
    def __init__(
        self,
        *,
        settings: Settings,
        llm_provider: LLMProvider | None = None,
    ) -> None:
        self._settings = settings
        self._llm_provider = llm_provider

    def enrich(
        self,
        session: Session,
        *,
        case_id: UUID,
        organization_id: UUID,
        analysis_run_id: UUID,
    ) -> ExplanationResult:
        input_data = self._build_input(
            session,
            case_id=case_id,
            organization_id=organization_id,
            analysis_run_id=analysis_run_id,
        )
        self._end_read_transaction(session)
        provider = self._llm_provider if self._llm_provider is not None else create_llm_provider(
            self._settings
        )
        if provider is None:
            explanation = build_explanation_fallback(input_data)
            validate_explanation_semantics(explanation=explanation, input_data=input_data)
            return ExplanationResult(
                explanation=explanation,
                explanation_source="TEMPLATE_FALLBACK",
                failure_category="unavailable",
            )
        try:
            explanation = asyncio.run(
                self._generate_with_provider(provider=provider, input_data=input_data)
            )
            provider_name = getattr(provider, "provider_name", "llm")
            model_name = getattr(provider, "model_name", None)
            return ExplanationResult(
                explanation=explanation,
                explanation_source="LLM",
                provider_name=provider_name,
                model_name=model_name,
            )
        except AIProviderError as exc:
            logger.info(
                "Explanation fallback for case=%s run=%s category=%s",
                case_id,
                analysis_run_id,
                exc.category,
            )
            explanation = build_explanation_fallback(input_data)
            validate_explanation_semantics(explanation=explanation, input_data=input_data)
            return ExplanationResult(
                explanation=explanation,
                explanation_source="TEMPLATE_FALLBACK",
                provider_name=getattr(provider, "provider_name", None),
                model_name=getattr(provider, "model_name", None),
                failure_category=exc.category,
            )

    async def _generate_with_provider(
        self,
        *,
        provider: LLMProvider,
        input_data: ExplanationInput,
    ) -> RecommendationExplanation:
        candidate = await provider.generate_structured(
            task=EXPLANATION_TASK,
            input=input_data,
            output_schema=RecommendationExplanation,
        )
        try:
            validated = RecommendationExplanation.model_validate(candidate.model_dump())
        except ValidationError as exc:
            raise AIProviderError("Explanation schema validation failed.") from exc
        validate_explanation_semantics(explanation=validated, input_data=input_data)
        return validated

    def _build_input(
        self,
        session: Session,
        *,
        case_id: UUID,
        organization_id: UUID,
        analysis_run_id: UUID,
    ) -> ExplanationInput:
        case = session.execute(
            select(RecoveryCase).where(
                RecoveryCase.id == case_id,
                RecoveryCase.organization_id == organization_id,
            )
        ).scalar_one()
        # The explanation must describe the action that will actually be
        # executed, which is not necessarily rank 1: the model's top choice can
        # be an advisory action RevLoop does not perform. Reading rank 1 here
        # would produce an explanation arguing for one action while `selected`
        # in the same response named another -- the same divergence that was
        # fixed on the case-detail read path. `select_candidate_row` is the one
        # shared definition of "selected".
        candidates = list(
            session.execute(
                select(RecoveryRecommendation).where(
                    RecoveryRecommendation.case_id == case_id,
                    RecoveryRecommendation.organization_id == organization_id,
                    RecoveryRecommendation.analysis_run_id == analysis_run_id,
                )
            ).scalars()
        )
        if not candidates:
            raise ValueError("No recommendations exist for this analysis run.")
        recommendation = select_candidate_row(candidates) or top_ranked_row(candidates)
        if recommendation is None:  # pragma: no cover - defensive
            raise ValueError("No recommendation could be selected for explanation.")
        if case.current_analysis_run_id != analysis_run_id:
            raise ValueError("Analysis run is not current for case.")

        probability = Decimal(str(recommendation.success_probability))
        confidence = Decimal(str(recommendation.confidence))
        evidence_factors = [
            EvidenceFactorInput(code=str(item["code"]), impact=str(item.get("impact", "MEDIUM")))
            for item in recommendation.factors
            if item.get("code")
        ]
        approved_evidence = approved_statements_for_factors(recommendation.factors)
        probability_phrase = format_probability_percent(probability)
        confidence_phrase = format_confidence_percent(confidence)
        amount_phrase = format_minor_amount(case.amount_at_risk_minor, case.currency)
        recovered_phrase = format_minor_amount(
            recommendation.expected_recovered_minor,
            case.currency,
        )
        approved_numeric = [
            probability_phrase,
            confidence_phrase,
            amount_phrase,
            recovered_phrase,
            str(recommendation.expected_recovered_minor),
            str(recommendation.expected_value_minor),
            str(case.amount_at_risk_minor),
            f"{probability}",
            f"{confidence}",
        ]
        return ExplanationInput(
            case_type=case.case_type,
            amount_minor=case.amount_at_risk_minor,
            currency=case.currency,
            failure_category=case.failure_category,
            selected_action=recommendation.action_type,
            success_probability=probability,
            expected_recovered_minor=recommendation.expected_recovered_minor,
            expected_value_minor=recommendation.expected_value_minor,
            confidence=confidence,
            evidence_factors=evidence_factors,
            policy=PolicyInput(
                eligible=bool(recommendation.policy_eligible),
                requires_approval=bool(recommendation.requires_approval),
                reasons=[str(reason) for reason in (recommendation.policy_reasons or [])],
            ),
            approved_evidence_statements=approved_evidence,
            approved_numeric_tokens=approved_numeric,
            allowed_probability_phrases=[probability_phrase],
            allowed_money_phrases=[amount_phrase, recovered_phrase],
            allowed_confidence_phrases=[confidence_phrase],
            selected_action_label=action_label(recommendation.action_type),
        )

    def _end_read_transaction(self, session: Session) -> None:
        """Close any read-only autobegin transaction before optional LLM latency."""
        if session.in_transaction():
            session.rollback()


def explanation_service_for_settings(
    settings: Settings,
    *,
    llm_provider: LLMProvider | None = None,
) -> RecommendationExplanationService:
    return RecommendationExplanationService(settings=settings, llm_provider=llm_provider)
