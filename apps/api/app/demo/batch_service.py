"""Demo batch/reset orchestration.

The batch is a pure offline evaluation: it reads no business tables, writes
nothing, and issues no provider, LLM or network calls. Only the reset summary
touches the database, and only to count what the seed just restored.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.demo.constants import DEMO_ORGANIZATION_ID, DEMO_SEED_VERSION
from app.demo.evaluation import (
    DEMO_BATCH_CASE_COUNT,
    CanonicalBatchResult,
    realized_recovery_rate,
    run_canonical_batch,
)
from app.demo.schemas import (
    DatasetProvenanceModel,
    DemoBatchResponse,
    DemoResetResponse,
    PolicySimulationSummary,
    ScorerProvenanceModel,
)
from app.models.recovery_case import RecoveryCase


def _summary(policy: dict[str, Any]) -> PolicySimulationSummary:
    """Map one canonical policy summary onto the response model.

    Straight field mapping — no metric is recomputed here, so the API cannot
    drift from the canonical evaluator's definitions.
    """
    return PolicySimulationSummary(
        number_of_cases=int(policy["number_of_cases"]),
        amount_at_risk_minor=int(policy["amount_at_risk_minor"]),
        expected_synthetic_recovered_minor=int(policy["expected_synthetic_recovered_minor"]),
        realized_synthetic_recovered_minor=int(policy["realized_synthetic_recovered_minor"]),
        realized_recovery_rate=realized_recovery_rate(policy),
        selected_intervention_count=int(policy["selected_intervention_count"]),
        contact_action_count=int(policy["contact_action_count"]),
        stop_count=int(policy["stop_count"]),
        no_selection_count=int(policy["no_selection_count"]),
    )


def to_response(result: CanonicalBatchResult) -> DemoBatchResponse:
    simulation = result.simulation
    return DemoBatchResponse(
        evaluation_label=str(simulation["evaluation_label"]),
        scorer=ScorerProvenanceModel(
            model_version=result.scorer.model_version,
            model_family=result.scorer.model_family,
            feature_schema_version=result.scorer.feature_schema_version,
        ),
        dataset=DatasetProvenanceModel(
            dataset_version=result.dataset.dataset_version,
            seed=result.dataset.seed,
            split=result.dataset.split,
            case_count=result.dataset.case_count,
        ),
        revloop_model_policy=_summary(simulation["revloop_model_policy"]),
        naive_baseline_policy=_summary(simulation["naive_baseline_policy"]),
        incremental_expected_recovered_minor=int(
            simulation["incremental_expected_recovered_minor"]
        ),
        incremental_realized_recovered_minor=int(
            simulation["incremental_realized_recovered_minor"]
        ),
    )


def run_demo_batch(case_count: int = DEMO_BATCH_CASE_COUNT) -> DemoBatchResponse:
    """Evaluate the canonical synthetic batch. No database, no provider calls."""
    return to_response(run_canonical_batch(case_count))


def describe_reset(session: Session, reset_performed: bool) -> DemoResetResponse:
    """Summarise the restored canonical demo state."""
    case_count = int(
        session.execute(
            select(func.count())
            .select_from(RecoveryCase)
            .where(RecoveryCase.organization_id == DEMO_ORGANIZATION_ID)
        ).scalar_one()
    )
    return DemoResetResponse(
        seed_version=DEMO_SEED_VERSION,
        reset_performed=reset_performed,
        organization_id=str(DEMO_ORGANIZATION_ID),
        recovery_case_count=case_count,
    )


__all__ = ["describe_reset", "run_demo_batch", "to_response"]
