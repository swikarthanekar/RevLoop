"""Demo batch evaluation — a thin adapter over the canonical Prompt 11 evaluator.

This module deliberately contains NO synthetic-world methodology of its own.

Prompt 10 owns the synthetic generator (case features, hidden latent
probability, Bernoulli label sampling, deterministic split). Prompt 11 owns the
offline policy simulation (frozen-model scoring, production policy/ranking, the
naive baseline, and the metric aggregation). Prompt 23's only job is to select a
deterministic cohort, invoke the canonical evaluator, and hand the result to the
HTTP layer.

Consequences worth stating explicitly:

- There is no second latent-probability model here, no Bernoulli resampling and
  no hash-derived outcome draws. The evaluation reuses the
  ``synthetic_latent_probability`` and ``recovered_within_72h`` values Prompt 10
  already generated for each (case, action) row.
- Candidate scoring uses the frozen selected Logistic Regression artifact
  (``lr-v1.0.0``). The heuristic fallback is never used here; if the trusted
  model cannot load or score, the batch fails closed rather than reporting
  fallback numbers under the selected model's name.
- The evaluator is pure: no database, no provider, no LLM, no network, no
  writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.demo.canonical_ml import (
    CanonicalEvaluationUnavailableError,
    canonical_dataset,
    canonical_modules,
    canonical_test_case_ids,
)
from app.ml.service import (
    ModelArtifactError,
    ModelInferenceError,
    load_trusted_model_bundle,
)

#: Explicit provenance for every synthetic evaluation result (API_CONTRACTS.md
#: section 12). Never reuse this label for provider-backed evidence.
SYNTHETIC_SIMULATION = "SYNTHETIC_SIMULATION"

#: Canonical label required by AI_ML_DESIGN.md section 5.5. Produced by the
#: canonical evaluator itself; mirrored here only for assertion in tests.
SYNTHETIC_POLICY_SIMULATION_LABEL = "SYNTHETIC POLICY SIMULATION"

#: The canonical split used for a held-out policy benchmark (AI_ML_DESIGN.md
#: section 6: "The test split is never used for model selection").
EVALUATION_SPLIT = "test"

#: Size of the demo cohort, taken from the front of the canonical TEST split in
#: sorted case-id order.
#:
#: The canonical test split holds 2,250 cases and evaluating all of them takes
#: roughly 57 seconds, which is not viable for a synchronous HTTP request. No
#: document defines a demo batch size, so this is a deliberate, reported
#: deviation from "evaluate the whole test cohort". The subset rule is stable and
#: policy-independent: it depends only on generated case IDs, never on features,
#: predictions, eligibility or outcomes, so neither policy can be advantaged.
#: Because the canonical evaluator processes each case independently, the subset
#: result is exactly the full-cohort result restricted to these cases.
DEMO_BATCH_CASE_COUNT = 250

_RATE_PRECISION = Decimal("0.0001")


@dataclass(frozen=True)
class ScorerProvenance:
    """Identity of the model that actually produced the probabilities."""

    model_version: str
    model_family: str
    feature_schema_version: str
    artifact_sha256: str


@dataclass(frozen=True)
class DatasetProvenance:
    """Identity of the synthetic world the evaluation ran against."""

    dataset_version: str
    feature_schema_version: str
    seed: int
    split: str
    case_count: int
    action_row_count: int


@dataclass(frozen=True)
class CanonicalBatchResult:
    """Raw canonical evaluator output plus the provenance of its inputs."""

    simulation: dict[str, Any]
    scorer: ScorerProvenance
    dataset: DatasetProvenance


def load_selected_model():
    """Load and validate the frozen selected model bundle.

    Delegates entirely to the trusted loader, which enforces trusted-local-path
    only, sidecar SHA256 agreement, bundle structure, and metadata validity. A
    request can never influence which artifact is loaded.
    """
    try:
        return load_trusted_model_bundle()
    except (ModelArtifactError, ModelInferenceError, ValueError) as exc:
        raise CanonicalEvaluationUnavailableError(
            message="Selected recovery model could not be loaded for evaluation.",
        ) from exc


def demo_cohort_frame(case_count: int = DEMO_BATCH_CASE_COUNT):
    """Rows for the deterministic demo cohort, drawn from the canonical TEST split."""
    dataset = canonical_dataset()
    selected_ids = set(canonical_test_case_ids()[:case_count])
    frame = dataset.frame
    return frame.loc[frame["case_id"].astype(str).isin(selected_ids)].copy()


def run_canonical_batch(case_count: int = DEMO_BATCH_CASE_COUNT) -> CanonicalBatchResult:
    """Run the canonical Prompt 11 policy simulation over the demo cohort.

    Every number returned is produced by ``simulate_policy_on_test_cases``; this
    function only assembles its inputs and records what they were.
    """
    modules = canonical_modules()
    dataset = canonical_dataset()
    bundle = load_selected_model()

    cohort = demo_cohort_frame(case_count)

    try:
        simulation = modules.evaluate.simulate_policy_on_test_cases(
            frame=cohort,
            pipeline=bundle.pipeline,
        )
    except CanonicalEvaluationUnavailableError:
        raise
    except Exception as exc:  # noqa: BLE001 - fail closed on any scoring failure
        raise CanonicalEvaluationUnavailableError(
            message="Canonical synthetic policy simulation failed.",
        ) from exc

    test_rows = cohort.loc[cohort["split"] == EVALUATION_SPLIT]
    return CanonicalBatchResult(
        simulation=simulation,
        scorer=ScorerProvenance(
            model_version=bundle.metadata.model_version,
            model_family=bundle.metadata.model_family,
            feature_schema_version=bundle.metadata.feature_schema_version,
            artifact_sha256=bundle.artifact_sha256,
        ),
        dataset=DatasetProvenance(
            dataset_version=dataset.dataset_version,
            feature_schema_version=dataset.feature_schema_version,
            seed=dataset.seed,
            split=EVALUATION_SPLIT,
            case_count=int(test_rows["case_id"].nunique()),
            action_row_count=int(len(test_rows)),
        ),
    )


def realized_recovery_rate(summary: dict[str, Any]) -> Decimal:
    """Quantize the canonical ``realized_recovery_rate`` for transport.

    The value and its denominator are the canonical evaluator's: recovered cases
    divided by cases evaluated, and exactly ``0`` when the cohort is empty. This
    only fixes the decimal representation; it does not redefine the metric.
    """
    return Decimal(str(summary["realized_recovery_rate"])).quantize(_RATE_PRECISION)


__all__ = [
    "DEMO_BATCH_CASE_COUNT",
    "EVALUATION_SPLIT",
    "SYNTHETIC_POLICY_SIMULATION_LABEL",
    "SYNTHETIC_SIMULATION",
    "CanonicalBatchResult",
    "DatasetProvenance",
    "ScorerProvenance",
    "demo_cohort_frame",
    "load_selected_model",
    "realized_recovery_rate",
    "run_canonical_batch",
]
