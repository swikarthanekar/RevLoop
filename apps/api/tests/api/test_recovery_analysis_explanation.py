# ruff: noqa: E402
pytest_plugins = ["tests.recovery.conftest"]


import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.ai.errors import (
    AIProviderAuthError,
    AIProviderRateLimitError,
    AIProviderResponseError,
    AIProviderTimeoutError,
)
from app.ai.explanations import RecommendationExplanationService
from app.ai.provider import FakeLLMProvider
from app.ai.schemas import RecommendationExplanation
from app.demo.constants import DEMO_ORGANIZATION_ID
from app.domain.enums import RecoveryCaseStatus
from app.models.recovery_case import RecoveryCase
from app.models.recovery_recommendation import RecoveryRecommendation
from tests.ai.fake_providers import build_grounded_explanation_provider
from tests.api.conftest import DEMO_AUTH_HEADERS
from tests.workflows.helpers import create_case, create_customer


def _seed_rank_one_recommendation(db_session, *, run_id: uuid.UUID):
    customer = create_customer(db_session, organization_id=DEMO_ORGANIZATION_ID)
    case = create_case(db_session, organization_id=DEMO_ORGANIZATION_ID, customer_id=customer.id)
    case.current_analysis_run_id = run_id
    db_session.add(
        RecoveryRecommendation(
            organization_id=DEMO_ORGANIZATION_ID,
            case_id=case.id,
            analysis_run_id=run_id,
            action_type="CREATE_PAYMENT_LINK",
            rank=1,
            success_probability=Decimal("0.820000"),
            expected_recovered_minor=409918,
            expected_value_minor=402500,
            confidence=Decimal("0.870000"),
            policy_eligible=True,
            requires_approval=False,
            policy_reasons=[],
            factors=[{"code": "ACTIVE_RAIL_DOWNTIME", "impact": "HIGH", "source": "DOWNTIME"}],
            model_version="test-model",
            feature_schema_version="recovery_features_v1",
        )
    )
    db_session.commit()
    return case


@pytest.mark.parametrize(
    ("error",),
    [
        (AIProviderTimeoutError("timeout"),),
        (AIProviderRateLimitError("rate"),),
        (AIProviderAuthError("auth"),),
        (AIProviderResponseError("bad"),),
    ],
)
def test_provider_failures_use_template_fallback(
    recovery_seeded_database,
    recovery_demo_settings,
    db_session,
    error: Exception,
) -> None:
    run_id = uuid.uuid4()
    case = _seed_rank_one_recommendation(db_session, run_id=run_id)
    provider = FakeLLMProvider(error=error)
    service = RecommendationExplanationService(
        settings=recovery_demo_settings,
        llm_provider=provider,
    )
    result = service.enrich(
        db_session,
        case_id=case.id,
        organization_id=DEMO_ORGANIZATION_ID,
        analysis_run_id=run_id,
    )
    assert result.explanation_source == "TEMPLATE_FALLBACK"
    assert provider.call_count == 1


def test_analyze_with_valid_llm_explanation(
    api_client,
    analyzable_case,
    monkeypatch,
) -> None:
    provider = build_grounded_explanation_provider()

    def factory(settings):
        return RecommendationExplanationService(settings=settings, llm_provider=provider)

    import app.api.routes.recovery_analysis as routes

    monkeypatch.setattr(routes, "_EXPLANATION_SERVICE_FACTORY", factory)
    response = api_client.post(
        f"/api/v1/recovery-cases/{analyzable_case.id}/analyze",
        headers=DEMO_AUTH_HEADERS,
        json={"reason": "MANUAL_ANALYSIS"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["explanation_source"] == "LLM"
    assert payload["explanation"]["summary"]
    assert provider.call_count == 1


def test_analyze_with_provider_timeout_still_succeeds(
    api_client,
    analyzable_case,
    monkeypatch,
) -> None:
    from app.ai.errors import AIProviderTimeoutError
    from app.ai.provider import FakeLLMProvider

    provider = FakeLLMProvider(error=AIProviderTimeoutError("timeout"))

    def factory(settings):
        return RecommendationExplanationService(settings=settings, llm_provider=provider)

    import app.api.routes.recovery_analysis as routes

    monkeypatch.setattr(routes, "_EXPLANATION_SERVICE_FACTORY", factory)
    response = api_client.post(
        f"/api/v1/recovery-cases/{analyzable_case.id}/analyze",
        headers=DEMO_AUTH_HEADERS,
        json={"reason": "MANUAL_ANALYSIS"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == RecoveryCaseStatus.RECOMMENDED.value
    assert payload["explanation_source"] == "TEMPLATE_FALLBACK"
    assert payload["selected"]["action_type"]
    assert payload["explanation"]["summary"]


def test_recommendation_snapshot_unchanged_after_explanation(
    api_client,
    analyzable_case,
    fresh_db_session,
    monkeypatch,
) -> None:
    provider = build_grounded_explanation_provider()

    def factory(settings):
        return RecommendationExplanationService(settings=settings, llm_provider=provider)

    import app.api.routes.recovery_analysis as routes

    monkeypatch.setattr(routes, "_EXPLANATION_SERVICE_FACTORY", factory)
    response = api_client.post(
        f"/api/v1/recovery-cases/{analyzable_case.id}/analyze",
        headers=DEMO_AUTH_HEADERS,
        json={"reason": "MANUAL_ANALYSIS"},
    )
    assert response.status_code == 200, response.text
    run_id = uuid.UUID(response.json()["analysis_run_id"])
    before = fresh_db_session.execute(
        select(RecoveryRecommendation).where(
            RecoveryRecommendation.analysis_run_id == run_id,
            RecoveryRecommendation.rank == 1,
        )
    ).scalar_one()
    snapshot = {
        "action_type": before.action_type,
        "rank": before.rank,
        "success_probability": Decimal(str(before.success_probability)),
        "expected_recovered_minor": before.expected_recovered_minor,
        "expected_value_minor": before.expected_value_minor,
        "confidence": Decimal(str(before.confidence)),
        "policy_eligible": before.policy_eligible,
        "requires_approval": before.requires_approval,
        "policy_reasons": list(before.policy_reasons or []),
        "factors": list(before.factors or []),
        "model_version": before.model_version,
        "feature_schema_version": before.feature_schema_version,
    }
    after = fresh_db_session.execute(
        select(RecoveryRecommendation).where(
            RecoveryRecommendation.id == before.id,
        )
    ).scalar_one()
    assert snapshot == {
        "action_type": after.action_type,
        "rank": after.rank,
        "success_probability": Decimal(str(after.success_probability)),
        "expected_recovered_minor": after.expected_recovered_minor,
        "expected_value_minor": after.expected_value_minor,
        "confidence": Decimal(str(after.confidence)),
        "policy_eligible": after.policy_eligible,
        "requires_approval": after.requires_approval,
        "policy_reasons": list(after.policy_reasons or []),
        "factors": list(after.factors or []),
        "model_version": after.model_version,
        "feature_schema_version": after.feature_schema_version,
    }


def test_commit_order_recommendation_visible_during_provider_call(
    recovery_seeded_database,
    recovery_demo_settings,
    db_session,
) -> None:
    customer = create_customer(db_session, organization_id=DEMO_ORGANIZATION_ID)
    case = create_case(db_session, organization_id=DEMO_ORGANIZATION_ID, customer_id=customer.id)
    run_id = uuid.uuid4()
    case.current_analysis_run_id = run_id
    recommendation = RecoveryRecommendation(
        organization_id=DEMO_ORGANIZATION_ID,
        case_id=case.id,
        analysis_run_id=run_id,
        action_type="CREATE_PAYMENT_LINK",
        rank=1,
        success_probability=Decimal("0.820000"),
        expected_recovered_minor=409918,
        expected_value_minor=402500,
        confidence=Decimal("0.870000"),
        policy_eligible=True,
        requires_approval=False,
        policy_reasons=[],
        factors=[{"code": "ACTIVE_RAIL_DOWNTIME", "impact": "HIGH", "source": "DOWNTIME"}],
        model_version="test-model",
        feature_schema_version="recovery_features_v1",
    )
    db_session.add(recommendation)
    db_session.commit()
    case_id = case.id

    observed: dict[str, object] = {}

    def pre_generate(_task, _input) -> None:
        verify = sessionmaker(bind=recovery_seeded_database, autoflush=False, autocommit=False)()
        try:
            persisted_case = verify.execute(
                select(RecoveryCase).where(RecoveryCase.id == case_id)
            ).scalar_one()
            persisted_rec = verify.execute(
                select(RecoveryRecommendation).where(
                    RecoveryRecommendation.analysis_run_id == run_id,
                    RecoveryRecommendation.rank == 1,
                )
            ).scalar_one()
            observed["run_id"] = persisted_case.current_analysis_run_id
            observed["probability"] = float(persisted_rec.success_probability)
        finally:
            verify.close()

    from app.ai.provider import FakeLLMProvider

    explanation = RecommendationExplanation(
        summary=(
            "Recommended: Create a payment link with an estimated recovery "
            "probability of 82%."
        ),
        evidence=["The payment rail shows active degradation."],
        safety=["No manual approval is required under current policy."],
        customer_impact="The customer receives a clear next step.",
    )
    provider = FakeLLMProvider(response=explanation, pre_generate=pre_generate)
    service = RecommendationExplanationService(
        settings=recovery_demo_settings,
        llm_provider=provider,
    )
    verify_session = sessionmaker(
        bind=recovery_seeded_database,
        autoflush=False,
        autocommit=False,
    )()
    try:
        result = service.enrich(
            verify_session,
            case_id=case_id,
            organization_id=DEMO_ORGANIZATION_ID,
            analysis_run_id=run_id,
        )
    finally:
        verify_session.close()
    assert observed["run_id"] == run_id
    assert observed["probability"] == 0.82
    assert result.explanation_source == "LLM"


def test_no_open_transaction_during_provider_call(
    recovery_seeded_database,
    recovery_demo_settings,
    db_session,
) -> None:
    run_id = uuid.uuid4()
    case = _seed_rank_one_recommendation(db_session, run_id=run_id)
    observed: dict[str, object] = {}

    def pre_generate(_task, _input) -> None:
        observed["in_transaction"] = db_session.in_transaction()
        verify = sessionmaker(bind=recovery_seeded_database, autoflush=False, autocommit=False)()
        try:
            persisted = verify.execute(
                select(RecoveryRecommendation).where(
                    RecoveryRecommendation.analysis_run_id == run_id,
                    RecoveryRecommendation.rank == 1,
                )
            ).scalar_one()
            observed["probability"] = float(persisted.success_probability)
        finally:
            verify.close()

    explanation = RecommendationExplanation(
        summary="Recommended: Create a payment link.",
        evidence=["The payment rail shows active degradation."],
        safety=["No manual approval is required under current policy."],
    )
    provider = FakeLLMProvider(response=explanation, pre_generate=pre_generate)
    service = RecommendationExplanationService(
        settings=recovery_demo_settings,
        llm_provider=provider,
    )
    result = service.enrich(
        db_session,
        case_id=case.id,
        organization_id=DEMO_ORGANIZATION_ID,
        analysis_run_id=run_id,
    )
    assert observed["in_transaction"] is False
    assert observed["probability"] == 0.82
    assert result.explanation_source == "LLM"


def test_analyze_api_no_open_transaction_during_provider(
    api_client,
    analyzable_case,
    monkeypatch,
) -> None:
    from app.ai.provider import CallableLLMProvider

    route_session_holder: dict[str, object] = {}
    observed: dict[str, object] = {}

    original_enrich = RecommendationExplanationService.enrich

    def enrich_with_capture(self, session, **kwargs):
        route_session_holder["session"] = session
        return original_enrich(self, session, **kwargs)

    monkeypatch.setattr(RecommendationExplanationService, "enrich", enrich_with_capture)

    async def handler(task, input, output_schema):
        session = route_session_holder.get("session")
        observed["in_transaction"] = bool(session and session.in_transaction())
        evidence = input.approved_evidence_statements[:1] or [
            "Current case evidence supports the selected action."
        ]
        return output_schema(
            summary=f"Recommended: {input.selected_action_label}.",
            evidence=evidence,
            safety=[],
        )

    provider = CallableLLMProvider(handler)

    def factory(settings):
        return RecommendationExplanationService(settings=settings, llm_provider=provider)

    import app.api.routes.recovery_analysis as routes

    monkeypatch.setattr(routes, "_EXPLANATION_SERVICE_FACTORY", factory)
    response = api_client.post(
        f"/api/v1/recovery-cases/{analyzable_case.id}/analyze",
        headers=DEMO_AUTH_HEADERS,
        json={"reason": "MANUAL_ANALYSIS"},
    )
    assert response.status_code == 200, response.text
    assert observed.get("in_transaction") is False
    assert response.json()["explanation_source"] == "LLM"
