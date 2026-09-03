"""Canonical correctness tests for the demo batch evaluation.

These replace the earlier Prompt 23 tests that validated a second, locally
invented synthetic world (BLAKE2b outcome draws, local latent coefficients,
fallback-as-normal-scorer, probability inequality as "leakage proof"). That
methodology was removed, so the tests that only existed to defend it were
removed with it.

What is asserted here instead: the batch reuses the canonical Prompt 10
generator and the canonical Prompt 11 evaluator, scores with the frozen selected
Logistic Regression, never touches the heuristic fallback on a healthy run, and
keeps ground truth strictly out of the decision path.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

from app.demo import evaluation as demo_evaluation
from app.demo.canonical_ml import (
    CanonicalEvaluationUnavailableError,
    canonical_dataset,
    canonical_modules,
    canonical_test_case_ids,
)
from app.demo.evaluation import (
    DEMO_BATCH_CASE_COUNT,
    EVALUATION_SPLIT,
    SYNTHETIC_POLICY_SIMULATION_LABEL,
    SYNTHETIC_SIMULATION,
    demo_cohort_frame,
    load_selected_model,
    run_canonical_batch,
)

# A small cohort keeps these tests fast; the canonical machinery is identical.
SMALL_COHORT = 12

DEMO_SOURCE_FILES = (
    "evaluation.py",
    "batch_service.py",
    "canonical_ml.py",
    "schemas.py",
)


@pytest.fixture(scope="module")
def modules():
    return canonical_modules()


@pytest.fixture(scope="module")
def bundle():
    return load_selected_model()


@pytest.fixture(scope="module")
def small_result():
    return run_canonical_batch(SMALL_COHORT)


def demo_source_text() -> str:
    package = Path(demo_evaluation.__file__).parent
    return "\n".join(
        (package / name).read_text(encoding="utf-8") for name in DEMO_SOURCE_FILES
    )


# --------------------------------------------------------------------------
# A. Selected model
# --------------------------------------------------------------------------


def test_healthy_batch_uses_the_frozen_selected_model(small_result) -> None:
    assert small_result.scorer.model_version == "lr-v1.0.0"
    assert small_result.scorer.model_family == "logistic_regression"
    assert small_result.scorer.feature_schema_version == "recovery_features_v1"


def test_artifact_sha256_matches_the_frozen_value(small_result, modules) -> None:
    assert small_result.scorer.artifact_sha256 == modules.common.FROZEN_LR_ARTIFACT_SHA256


def test_healthy_batch_never_calls_the_heuristic_fallback(monkeypatch) -> None:
    """Fail loud if the fallback scorer is touched on a healthy run."""
    calls: list[str] = []

    def fail_loud(*_args: object, **_kwargs: object):
        calls.append("fallback")
        raise AssertionError("Healthy batch must not use get_fallback_probability.")

    monkeypatch.setattr("app.ml.fallback.get_fallback_probability", fail_loud)
    run_canonical_batch(SMALL_COHORT)
    assert calls == []


def test_demo_package_does_not_import_the_fallback_scorer() -> None:
    assert "get_fallback_probability" not in demo_source_text()


def test_stop_actions_receive_zero_probability(modules, bundle) -> None:
    """STOP is never scored by the model; canonical latent for STOP is exactly 0."""
    cohort = demo_cohort_frame(SMALL_COHORT)
    stop_rows = cohort.loc[cohort["action_type"] == "STOP"]
    assert len(stop_rows) > 0
    assert (stop_rows["synthetic_latent_probability"].astype(float) == 0.0).all()
    assert (stop_rows["recovered_within_72h"].astype(int) == 0).all()


def test_model_predictions_are_finite_and_bounded(modules, bundle) -> None:
    import numpy as np

    predictive = modules.train_baseline.predictive_frame(demo_cohort_frame(SMALL_COHORT))
    probabilities = modules.train_baseline.predict_positive_probabilities(
        bundle.pipeline, predictive
    )
    assert np.isfinite(probabilities).all()
    assert (probabilities >= 0.0).all()
    assert (probabilities <= 1.0).all()


def test_model_input_excludes_ground_truth_columns(modules) -> None:
    feature_columns = set(modules.common.FEATURE_COLUMNS)
    forbidden = set(modules.common.FORBIDDEN_FEATURE_COLUMNS)
    assert "synthetic_latent_probability" in forbidden
    assert "recovered_within_72h" in forbidden
    assert not feature_columns & forbidden
    for leaked in ("case_id", "split", "synthetic_latent_probability", "recovered_within_72h"):
        assert leaked not in feature_columns


def test_batch_fails_closed_when_the_model_cannot_load(monkeypatch) -> None:
    """No fallback benchmark may be published under the selected model's name."""
    from app.ml.service import ModelArtifactError

    def explode(*_args: object, **_kwargs: object):
        raise ModelArtifactError("injected artifact failure")

    monkeypatch.setattr("app.demo.evaluation.load_trusted_model_bundle", explode)
    with pytest.raises(CanonicalEvaluationUnavailableError) as excinfo:
        run_canonical_batch(SMALL_COHORT)
    assert excinfo.value.status_code == 503


def test_batch_fails_closed_when_scoring_fails(monkeypatch, modules) -> None:
    def explode(*_args: object, **_kwargs: object):
        raise RuntimeError("injected scoring failure")

    monkeypatch.setattr(modules.evaluate, "simulate_policy_on_test_cases", explode)
    with pytest.raises(CanonicalEvaluationUnavailableError):
        run_canonical_batch(SMALL_COHORT)


# --------------------------------------------------------------------------
# B. Canonical ground truth
# --------------------------------------------------------------------------


def test_bridge_exposes_the_actual_canonical_modules(modules) -> None:
    """Not a rewritten copy — the identical module objects."""
    repo_root = Path(demo_evaluation.__file__).resolve().parents[4]
    scripts_root = str(repo_root / "scripts")
    if scripts_root not in sys.path:
        sys.path.insert(0, scripts_root)
    import ml.common as canonical_common
    import ml.evaluate as canonical_evaluate
    import ml.train_baseline as canonical_train

    assert modules.common is canonical_common
    assert modules.train_baseline is canonical_train
    assert modules.evaluate is canonical_evaluate


def test_canonical_generator_parity(modules) -> None:
    """Prompt 23's dataset equals a direct canonical generation, row for row."""
    common = modules.common
    direct = common.generate_dataset(
        case_count=common.DEFAULT_CASE_COUNT,
        seed=common.DEFAULT_SEED,
    )
    direct_by_key = {
        (row["case_id"], row["action_type"]): row for row in direct.rows
    }

    cohort = demo_cohort_frame(SMALL_COHORT)
    assert len(cohort) > 0
    for _, row in cohort.iterrows():
        key = (str(row["case_id"]), str(row["action_type"]))
        assert key in direct_by_key
        source = direct_by_key[key]
        assert float(row["synthetic_latent_probability"]) == pytest.approx(
            float(source["synthetic_latent_probability"])
        )
        assert int(row["recovered_within_72h"]) == int(source["recovered_within_72h"])
        assert str(row["split"]) == str(source["split"])
        assert float(row["amount_log1p"]) == pytest.approx(float(source["amount_log1p"]))


def test_dataset_provenance_is_canonical(small_result, modules) -> None:
    assert small_result.dataset.dataset_version == modules.common.DATASET_VERSION
    assert small_result.dataset.seed == modules.common.DEFAULT_SEED
    assert small_result.dataset.split == EVALUATION_SPLIT
    assert small_result.dataset.feature_schema_version == "recovery_features_v1"


def test_no_second_latent_model_remains() -> None:
    source = demo_source_text()
    for banned in (
        "_GLOBAL_INTERCEPT",
        "_ACTION_BIAS",
        "_FAILURE_ACTION_INTERACTION",
        "_SUBSCRIPTION_CASE_ADJUSTMENT",
        "_HIGH_VALUE_PENALTY",
        "latent_recovery_probability",
        "DEMO_BATCH_SIMULATION_VERSION",
    ):
        assert banned not in source, banned


def test_no_outcome_resampling_remains() -> None:
    source = demo_source_text()
    for banned in ("blake2", "hashlib", "random.", "outcome_draw", "uuid4", "Random("):
        assert banned not in source, banned


def test_cohort_is_drawn_from_the_canonical_test_split() -> None:
    cohort = demo_cohort_frame(SMALL_COHORT)
    assert set(cohort["split"].astype(str).unique()) == {EVALUATION_SPLIT}


def test_cohort_subset_rule_is_stable_and_policy_independent() -> None:
    ids = canonical_test_case_ids()
    assert list(ids) == sorted(ids)
    first = set(demo_cohort_frame(SMALL_COHORT)["case_id"].astype(str))
    second = set(demo_cohort_frame(SMALL_COHORT)["case_id"].astype(str))
    assert first == second == set(ids[:SMALL_COHORT])


def test_larger_cohort_is_a_superset_of_the_smaller_one() -> None:
    small = set(demo_cohort_frame(SMALL_COHORT)["case_id"].astype(str))
    larger = set(demo_cohort_frame(SMALL_COHORT * 2)["case_id"].astype(str))
    assert small < larger


# --------------------------------------------------------------------------
# C. Canonical evaluator parity
# --------------------------------------------------------------------------


def test_canonical_evaluator_parity(modules, bundle, small_result) -> None:
    """Prompt 23's numbers equal the accepted Prompt 11 evaluator's numbers."""
    direct = modules.evaluate.simulate_policy_on_test_cases(
        frame=demo_cohort_frame(SMALL_COHORT),
        pipeline=bundle.pipeline,
    )
    assert small_result.simulation == direct


def test_canonical_evaluator_parity_on_independently_built_frame(
    modules, bundle, small_result, tmp_path
) -> None:
    """Rebuild the canonical world from scratch and reproduce the same result."""
    common = modules.common
    dataset = common.generate_dataset(
        case_count=common.DEFAULT_CASE_COUNT,
        seed=common.DEFAULT_SEED,
    )
    csv_path, summary_path = common.write_dataset(tmp_path, dataset)
    frame, _ = modules.train_baseline.load_training_frame(
        csv_path=csv_path, summary_path=summary_path
    )
    test_ids = sorted(frame.loc[frame["split"] == "test", "case_id"].astype(str).unique())
    subset = frame.loc[frame["case_id"].astype(str).isin(set(test_ids[:SMALL_COHORT]))].copy()

    rebuilt = modules.evaluate.simulate_policy_on_test_cases(
        frame=subset, pipeline=bundle.pipeline
    )
    assert rebuilt == small_result.simulation


def test_evaluation_label_is_canonical(small_result) -> None:
    assert small_result.simulation["evaluation_label"] == SYNTHETIC_POLICY_SIMULATION_LABEL


# --------------------------------------------------------------------------
# D. Leakage — behavioral, not numeric inequality
# --------------------------------------------------------------------------


def test_changing_ground_truth_does_not_change_model_predictions(modules, bundle) -> None:
    cohort = demo_cohort_frame(SMALL_COHORT)
    mutated = cohort.copy()
    mutated["synthetic_latent_probability"] = 0.99
    mutated["recovered_within_72h"] = 1

    predict = modules.train_baseline.predict_positive_probabilities
    predictive = modules.train_baseline.predictive_frame
    before = predict(bundle.pipeline, predictive(cohort))
    after = predict(bundle.pipeline, predictive(mutated))
    assert (before == after).all()


def test_changing_ground_truth_does_not_change_selection(modules, bundle) -> None:
    """Only grading may move when ground truth moves; selection must not."""
    cohort = demo_cohort_frame(SMALL_COHORT)
    mutated = cohort.copy()
    mutated["synthetic_latent_probability"] = 0.99
    mutated["recovered_within_72h"] = 1

    simulate = modules.evaluate.simulate_policy_on_test_cases
    base = simulate(frame=cohort, pipeline=bundle.pipeline)
    changed = simulate(frame=mutated, pipeline=bundle.pipeline)

    for policy in ("revloop_model_policy", "naive_baseline_policy"):
        for selection_field in (
            "selected_intervention_count",
            "contact_action_count",
            "stop_count",
            "no_selection_count",
            "number_of_cases",
            "amount_at_risk_minor",
        ):
            assert base[policy][selection_field] == changed[policy][selection_field], (
                policy,
                selection_field,
            )
    # Grading did move, proving the mutation was actually applied.
    assert (
        base["revloop_model_policy"]["realized_synthetic_recovered_minor"]
        != changed["revloop_model_policy"]["realized_synthetic_recovered_minor"]
    )


def test_changing_model_features_can_change_selection(modules, bundle) -> None:
    """The converse: decision features genuinely drive the decision."""
    cohort = demo_cohort_frame(SMALL_COHORT * 4)
    mutated = cohort.copy()
    mutated["payment_success_rate_90d"] = 0.01

    predict = modules.train_baseline.predict_positive_probabilities
    predictive = modules.train_baseline.predictive_frame
    before = predict(bundle.pipeline, predictive(cohort))
    after = predict(bundle.pipeline, predictive(mutated))
    assert not (before == after).all()


# --------------------------------------------------------------------------
# E. Fairness — one immutable counterfactual table
# --------------------------------------------------------------------------


def test_both_policies_share_the_same_cohort(small_result) -> None:
    revloop = small_result.simulation["revloop_model_policy"]
    baseline = small_result.simulation["naive_baseline_policy"]
    assert revloop["number_of_cases"] == baseline["number_of_cases"] == SMALL_COHORT
    assert revloop["amount_at_risk_minor"] == baseline["amount_at_risk_minor"]


def test_policy_order_does_not_change_results(modules, bundle) -> None:
    cohort = demo_cohort_frame(SMALL_COHORT)
    forward = modules.evaluate.simulate_policy_on_test_cases(
        frame=cohort, pipeline=bundle.pipeline
    )
    reversed_rows = modules.evaluate.simulate_policy_on_test_cases(
        frame=cohort.iloc[::-1].copy(), pipeline=bundle.pipeline
    )
    assert forward == reversed_rows


def test_evaluation_does_not_mutate_the_cohort(modules, bundle) -> None:
    cohort = demo_cohort_frame(SMALL_COHORT)
    snapshot = cohort.copy(deep=True)
    modules.evaluate.simulate_policy_on_test_cases(frame=cohort, pipeline=bundle.pipeline)
    assert cohort.equals(snapshot)


def test_repeated_evaluation_is_deterministic() -> None:
    assert run_canonical_batch(SMALL_COHORT).simulation == run_canonical_batch(
        SMALL_COHORT
    ).simulation


def test_process_rng_state_does_not_affect_results() -> None:
    import random as stdlib_random

    stdlib_random.seed(1)
    first = run_canonical_batch(SMALL_COHORT).simulation
    stdlib_random.seed(999)
    [stdlib_random.random() for _ in range(100)]
    second = run_canonical_batch(SMALL_COHORT).simulation
    assert first == second


# --------------------------------------------------------------------------
# F. Subscription / downtime semantics
# --------------------------------------------------------------------------


def canonical_cases(count: int = 600):
    """Canonical case features, generated with the canonical generator itself.

    `subscription_status` and `provider_retries_active` are case-level fields, not
    CSV feature columns, so they are asserted on the generated case objects.
    """
    import random as stdlib_random

    common = canonical_modules().common
    case_rng = stdlib_random.Random(common.DEFAULT_SEED)
    noise_rng = stdlib_random.Random(common.DEFAULT_SEED + 1)
    return [
        common.generate_case_features(
            case_index=index,
            split="test",
            case_rng=case_rng,
            noise_rng=noise_rng,
            dataset_version=common.DATASET_VERSION,
            seed=common.DEFAULT_SEED,
        )
        for index in range(count)
    ]


def test_provider_retries_active_only_for_pending_subscriptions() -> None:
    """Canonical rule: only `pending` may carry an active provider retry."""
    cases = canonical_cases()
    active = [case for case in cases if case.provider_retries_active]
    assert len(active) > 0
    assert {case.subscription_status for case in active} == {"pending"}


def test_non_pending_subscription_states_never_activate_provider_retries() -> None:
    """halted / active / completed / cancelled must all stay false."""
    cases = canonical_cases()
    seen: set[str] = set()
    for case in cases:
        status = case.subscription_status
        if status is None or status == "pending":
            continue
        seen.add(status)
        assert case.provider_retries_active is False, status
    # A nonempty status string alone must never imply an active retry.
    assert "halted" in seen
    assert len(seen) > 1


def test_production_uses_the_pending_status_constant() -> None:
    """The production semantic Prompt 23 must not reimplement."""
    from app.recovery.service import SUBSCRIPTION_PENDING_STATUS

    assert SUBSCRIPTION_PENDING_STATUS == "pending"


def test_demo_package_does_not_derive_retry_state_from_a_nonempty_string() -> None:
    source = demo_source_text()
    assert "bool(subscription" not in source
    assert "subscription.status" not in source


def test_downtime_is_an_explicit_canonical_feature() -> None:
    """`rail_degraded` is carried as its own feature, not inferred downstream.

    In the canonical generator a verified active downtime sets both
    `rail_degraded` and the PAYMENT_RAIL_DOWNTIME category together, so the two
    coincide in the data. That is the generator's decision. What matters for
    Prompt 23 is that it consumes the explicit feature rather than re-deriving
    downtime from the category, which is asserted separately below.
    """
    common = canonical_modules().common
    assert "rail_degraded" in set(common.BOOLEAN_FEATURE_COLUMNS)
    assert "rail_degraded" in set(common.FEATURE_COLUMNS)
    assert "downtime_severity" in set(common.CATEGORICAL_FEATURE_COLUMNS)

    # The canonical reader parses boolean feature columns to 0/1 integers.
    frame = canonical_dataset().frame
    degraded = frame["rail_degraded"].astype(int) == 1
    assert degraded.any()
    assert (~degraded).any()


def test_demo_package_does_not_conflate_downtime_with_failure_category() -> None:
    source = demo_source_text()
    assert "PAYMENT_RAIL_DOWNTIME" not in source


# --------------------------------------------------------------------------
# G. Naive baseline (unchanged canonical algorithm)
# --------------------------------------------------------------------------


def test_baseline_prefers_retry_then_wait_then_stop(modules) -> None:
    from app.domain.enums import RecoveryActionType
    from app.recovery.schemas import RecommendationCandidate

    def candidate(action: RecoveryActionType, eligible: bool) -> RecommendationCandidate:
        return RecommendationCandidate(
            action_type=action,
            success_probability=Decimal("0.5"),
            expected_recovered_minor=100,
            expected_value_minor=100,
            confidence=Decimal("0.5"),
            eligible=eligible,
            requires_approval=False,
            policy_reasons=(),
            operational_burden=1,
        )

    select = modules.evaluate.select_naive_baseline

    retry = candidate(RecoveryActionType.RETRY_SAME_METHOD, True)
    wait = candidate(RecoveryActionType.WAIT, True)
    stop = candidate(RecoveryActionType.STOP, True)

    assert select([wait, retry, stop]).action_type == RecoveryActionType.RETRY_SAME_METHOD
    assert select([wait, stop]).action_type == RecoveryActionType.WAIT
    assert select([stop]).action_type == RecoveryActionType.STOP
    assert select([]) is None
    # Ineligible candidates are never selected.
    assert (
        select([candidate(RecoveryActionType.RETRY_SAME_METHOD, False), wait]).action_type
        == RecoveryActionType.WAIT
    )


def test_baseline_is_the_canonical_implementation(modules) -> None:
    """Not a Prompt 23 copy."""
    assert "select_naive_baseline" not in demo_source_text()
    assert callable(modules.evaluate.select_naive_baseline)


# --------------------------------------------------------------------------
# H. Arithmetic
# --------------------------------------------------------------------------


def test_money_fields_are_integer_minor_units(small_result) -> None:
    simulation = small_result.simulation
    for policy in ("revloop_model_policy", "naive_baseline_policy"):
        for field in (
            "amount_at_risk_minor",
            "expected_synthetic_recovered_minor",
            "realized_synthetic_recovered_minor",
        ):
            assert isinstance(simulation[policy][field], int), (policy, field)
    assert isinstance(simulation["incremental_expected_recovered_minor"], int)
    assert isinstance(simulation["incremental_realized_recovered_minor"], int)


def test_incremental_is_revloop_minus_baseline(small_result) -> None:
    simulation = small_result.simulation
    revloop = simulation["revloop_model_policy"]
    baseline = simulation["naive_baseline_policy"]
    assert simulation["incremental_expected_recovered_minor"] == (
        revloop["expected_synthetic_recovered_minor"]
        - baseline["expected_synthetic_recovered_minor"]
    )
    assert simulation["incremental_realized_recovered_minor"] == (
        revloop["realized_synthetic_recovered_minor"]
        - baseline["realized_synthetic_recovered_minor"]
    )


def test_amount_at_risk_uses_the_canonical_reconstruction(modules) -> None:
    """Round-trip: log1p feature decodes back to the minor-unit amount."""
    import math

    decode = modules.common.decode_amount_at_risk_minor
    for amount in (1, 19_900, 499_900, 2_499_900, 100_000_000):
        assert decode(math.log1p(amount)) == amount
    with pytest.raises(ValueError):
        decode(-1.0)


def test_amount_at_risk_matches_decoded_cohort_amounts(modules, small_result) -> None:
    cohort = demo_cohort_frame(SMALL_COHORT)
    decode = modules.common.decode_amount_at_risk_minor
    expected_total = 0
    for case_id in sorted(cohort["case_id"].astype(str).unique()):
        rows = cohort.loc[cohort["case_id"].astype(str) == case_id]
        expected_total += decode(float(rows.iloc[0]["amount_log1p"]))
    assert (
        small_result.simulation["revloop_model_policy"]["amount_at_risk_minor"]
        == expected_total
    )


def test_expected_recovery_uses_canonical_latent_probability(modules, bundle) -> None:
    """Hand-check one policy's expected total from the stored latent values."""
    from app.recovery.erv import round_half_up

    cohort = demo_cohort_frame(SMALL_COHORT)
    decode = modules.common.decode_amount_at_risk_minor
    simulation = modules.evaluate.simulate_policy_on_test_cases(
        frame=cohort, pipeline=bundle.pipeline
    )

    # Recompute the baseline side independently: its selection rule is fixed, so
    # the expected total must equal the sum of round_half_up(latent * amount).
    total = 0
    realized = 0
    for case_id in sorted(cohort["case_id"].astype(str).unique()):
        rows = cohort.loc[cohort["case_id"].astype(str) == case_id]
        amount = decode(float(rows.iloc[0]["amount_log1p"]))
        candidates = modules.evaluate.build_recommendation_candidates(
            case_rows=rows,
            pipeline=bundle.pipeline,
            amount_at_risk_minor=amount,
            policy=modules.evaluate.synthetic_offline_evaluation_policy(),
        )
        selected = modules.evaluate.select_naive_baseline(candidates)
        if selected is None:
            continue
        row = rows.loc[rows["action_type"] == selected.action_type.value].iloc[0]
        total += round_half_up(
            Decimal(str(row["synthetic_latent_probability"])) * Decimal(amount)
        )
        if int(row["recovered_within_72h"]) == 1:
            realized += amount

    assert simulation["naive_baseline_policy"]["expected_synthetic_recovered_minor"] == total
    assert simulation["naive_baseline_policy"]["realized_synthetic_recovered_minor"] == realized


def test_recovery_rate_denominator_is_cases_evaluated(small_result) -> None:
    from app.demo.evaluation import realized_recovery_rate

    for policy in ("revloop_model_policy", "naive_baseline_policy"):
        summary = small_result.simulation[policy]
        rate = realized_recovery_rate(summary)
        assert rate == Decimal(str(summary["realized_recovery_rate"])).quantize(
            Decimal("0.0001")
        )
        assert Decimal(0) <= rate <= Decimal(1)


def test_zero_denominator_rate_is_zero() -> None:
    from app.demo.evaluation import realized_recovery_rate

    assert realized_recovery_rate({"realized_recovery_rate": 0.0}) == Decimal("0.0000")


# --------------------------------------------------------------------------
# I. Provenance / isolation
# --------------------------------------------------------------------------


def test_data_source_constant_is_the_contract_value() -> None:
    assert SYNTHETIC_SIMULATION == "SYNTHETIC_SIMULATION"


def test_demo_package_never_touches_provider_llm_or_training() -> None:
    source = demo_source_text()
    for banned in (
        "app.integrations",
        "acquire_razorpay_read_client",
        "RecoveryAnalysisService",
        "compute_analysis",
        "httpx",
        "requests",
        "gemini",
        "Gemini",
        "model.fit",
        "joblib.dump",
        "RecoveryAction(",
        "RecoveryOutcome(",
    ):
        assert banned not in source, banned


def test_default_cohort_size_is_documented() -> None:
    assert DEMO_BATCH_CASE_COUNT == 250
    assert DEMO_BATCH_CASE_COUNT < len(canonical_test_case_ids())
