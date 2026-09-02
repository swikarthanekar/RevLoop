"""Recovery analysis service tests."""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import func, select

from app.domain.enums import RecoveryActionType
from app.ml.schemas import ModelInferenceResult
from app.ml.service import ModelInferenceError, RecoveryPropensityModelService
from app.models.recovery_case import RecoveryCase
from app.models.recovery_recommendation import RecoveryRecommendation
from app.recovery.ranking import rank_candidates, select_recommendation
from app.recovery.schemas import RecommendationCandidate
from app.recovery.service import (
    RecoveryAnalysisService,
    build_model_metadata_factors,
)
from app.repositories.recovery_analysis import RecoveryAnalysisRepository
from tests.recovery.conftest import CANONICAL_ARTIFACT_SHA256
from tests.recovery.helpers import quantize_priority_score


def test_build_model_metadata_factors_includes_artifact_hash() -> None:
    inference = ModelInferenceResult(
        model_version="lr-v1.0.0",
        model_family="logistic_regression",
        feature_schema_version="recovery_features_v1",
        artifact_sha256=CANONICAL_ARTIFACT_SHA256,
        source="model",
        fallback_reason=None,
        probabilities=(),
    )
    factors = build_model_metadata_factors(inference)
    assert factors[0]["artifact_sha256"] == CANONICAL_ARTIFACT_SHA256
    assert factors[0]["model_family"] == "logistic_regression"


def test_frozen_lr_scores_boolean_runtime_features(analyzable_case, db_session) -> None:
    """Regression: boolean ML features must be int-cast before sklearn inference."""
    case = analyzable_case
    service = RecoveryAnalysisService(db_session)
    result = service.compute_analysis(case=case)
    assert result.inference.source == "model"
    assert result.inference.model_family == "logistic_regression"
    assert all(
        candidate.success_probability >= Decimal("0") for candidate in result.ranked_candidates
    )


def test_compute_analysis_uses_model_and_persists_metadata(analyzable_case, db_session) -> None:
    case = analyzable_case
    service = RecoveryAnalysisService(db_session)
    result = service.compute_analysis(case=case)

    assert result.inference.source == "model"
    assert result.inference.model_family == "logistic_regression"
    assert result.inference.feature_schema_version == "recovery_features_v1"
    assert result.inference.artifact_sha256 == CANONICAL_ARTIFACT_SHA256
    assert result.ranked_candidates
    assert result.selected is not None
    assert result.recommendation_rows[0].model_version == result.inference.model_version
    assert (
        result.recommendation_rows[0].feature_schema_version
        == result.inference.feature_schema_version
    )
    metadata_factor = next(
        factor
        for factor in result.recommendation_rows[0].factors
        if factor["code"] == "MODEL_METADATA"
    )
    assert metadata_factor["artifact_sha256"] == CANONICAL_ARTIFACT_SHA256


def test_persist_analysis_writes_immutable_recommendations(analyzable_case, db_session) -> None:
    case = analyzable_case
    service = RecoveryAnalysisService(db_session)
    first = service.compute_analysis(case=case)
    service.persist_analysis(case=case, result=first)

    second_run_id = uuid.uuid4()
    second = service.compute_analysis(case=case, analysis_run_id=second_run_id)
    service.persist_analysis(case=case, result=second)

    first_count = db_session.execute(
        select(func.count())
        .select_from(RecoveryRecommendation)
        .where(
            RecoveryRecommendation.case_id == case.id,
            RecoveryRecommendation.analysis_run_id == first.analysis_run_id,
        )
    ).scalar_one()
    second_count = db_session.execute(
        select(func.count())
        .select_from(RecoveryRecommendation)
        .where(
            RecoveryRecommendation.case_id == case.id,
            RecoveryRecommendation.analysis_run_id == second.analysis_run_id,
        )
    ).scalar_one()
    assert first_count == len(first.ranked_candidates)
    assert second_count == len(second.ranked_candidates)

    first_rows = db_session.execute(
        select(RecoveryRecommendation).where(
            RecoveryRecommendation.analysis_run_id == first.analysis_run_id
        )
    ).scalars().all()
    assert all(row.analysis_run_id == first.analysis_run_id for row in first_rows)


def test_model_fallback_persists_reason(analyzable_case, db_session) -> None:
    case = analyzable_case
    failing_model = MagicMock(spec=RecoveryPropensityModelService)
    failing_model.score_actions.side_effect = ModelInferenceError("inference failed")

    service = RecoveryAnalysisService(db_session, propensity_model=failing_model)
    result = service.compute_analysis(case=case)

    assert result.inference.source == "fallback"
    assert result.inference.fallback_reason == "inference failed"
    assert result.inference.model_version == "heuristic_fallback_v1"
    fallback_factor = next(
        factor
        for factor in result.recommendation_rows[0].factors
        if factor["code"] == "INFERENCE_FALLBACK"
    )
    assert "inference failed" in fallback_factor["source"]


def test_model_unavailable_without_fallback_raises(analyzable_case, db_session) -> None:
    from app.recovery.service import ModelUnavailableError

    case = analyzable_case
    failing_model = MagicMock(spec=RecoveryPropensityModelService)
    failing_model.score_actions.side_effect = ModelInferenceError("inference failed")

    service = RecoveryAnalysisService(
        db_session,
        propensity_model=failing_model,
        allow_model_fallback=False,
    )
    with pytest.raises(ModelUnavailableError):
        service.compute_analysis(case=case)


def test_invalid_feature_schema_version_rejected() -> None:
    service = RecoveryPropensityModelService()
    with pytest.raises(ModelInferenceError, match="Unsupported feature schema version"):
        service.score_actions(
            features=MagicMock(feature_schema_version="recovery_features_v2"),
            actions=[RecoveryActionType.WAIT],
        )


def test_stop_safety_selection_when_no_positive_erv() -> None:
    candidates = rank_candidates(
        [
            RecommendationCandidate(
                action_type=RecoveryActionType.CREATE_PAYMENT_LINK,
                success_probability=Decimal("0.80"),
                expected_recovered_minor=100,
                expected_value_minor=0,
                confidence=Decimal("0.80"),
                eligible=True,
                requires_approval=False,
                operational_burden=2,
            ),
            RecommendationCandidate(
                action_type=RecoveryActionType.STOP,
                success_probability=Decimal("0"),
                expected_recovered_minor=0,
                expected_value_minor=0,
                confidence=Decimal("0.90"),
                eligible=True,
                requires_approval=False,
                operational_burden=6,
            ),
        ]
    )
    selected = select_recommendation(candidates)
    assert selected is not None
    assert selected.action_type == RecoveryActionType.STOP


def test_deterministic_ranking_preserved() -> None:
    payload = [
        RecommendationCandidate(
            action_type=RecoveryActionType.WAIT,
            success_probability=Decimal("0.70"),
            expected_recovered_minor=200,
            expected_value_minor=200,
            confidence=Decimal("0.80"),
            eligible=True,
            requires_approval=False,
            operational_burden=0,
        ),
        RecommendationCandidate(
            action_type=RecoveryActionType.CREATE_PAYMENT_LINK,
            success_probability=Decimal("0.70"),
            expected_recovered_minor=200,
            expected_value_minor=200,
            confidence=Decimal("0.80"),
            eligible=True,
            requires_approval=False,
            operational_burden=2,
        ),
    ]
    first = rank_candidates(payload)
    second = rank_candidates(payload)
    assert [candidate.action_type for candidate in first] == [
        candidate.action_type for candidate in second
    ]


def test_repository_count_for_run(analyzable_case, db_session) -> None:
    case = analyzable_case
    organization_id = case.organization_id
    service = RecoveryAnalysisService(db_session)
    result = service.compute_analysis(case=case)
    service.persist_analysis(case=case, result=result)

    repo = RecoveryAnalysisRepository(db_session)
    assert repo.count_recommendations_for_run(
        case_id=case.id,
        organization_id=organization_id,
        analysis_run_id=result.analysis_run_id,
    ) == len(result.ranked_candidates)

    refreshed = db_session.execute(
        select(RecoveryCase).where(RecoveryCase.id == case.id)
    ).scalar_one()
    assert refreshed.current_analysis_run_id == result.analysis_run_id
    assert refreshed.priority_score == quantize_priority_score(result.priority_score)
