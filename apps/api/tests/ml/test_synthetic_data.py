"""Tests for synthetic action-level ML dataset generation."""

from __future__ import annotations

import csv
import hashlib
import random
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
for path in (REPO_ROOT / "apps" / "api", REPO_ROOT / "scripts"):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from ml.common import (  # noqa: E402
    CSV_COLUMNS,
    DATASET_VERSION,
    DEFAULT_SEED,
    FEATURE_COLUMNS,
    FORBIDDEN_FEATURE_COLUMNS,
    SyntheticCaseFeatures,
    SyntheticPaymentHistory,
    _sample_payment_history,
    candidate_context_from_case,
    compute_latent_probability,
    deterministic_case_id,
    effective_split_seed,
    generate_case_features,
    generate_dataset,
    read_csv_rows,
    write_dataset,
)

from app.domain.enums import CaseType, FailureCategory, RecoveryActionType  # noqa: E402
from app.recovery.candidates import generate_candidates  # noqa: E402
from app.recovery.schemas import FEATURE_SCHEMA_VERSION, CandidateGenerationContext  # noqa: E402


def _read_csv_header(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        return next(csv.reader(handle))


def _row_without_split(row: dict) -> dict:
    return {key: value for key, value in row.items() if key != "split"}


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _base_case(**overrides) -> SyntheticCaseFeatures:
    base = SyntheticCaseFeatures(
        case_index=0,
        case_id="case-test",
        split="train",
        case_type=CaseType.PAYMENT_FAILURE,
        failure_category=FailureCategory.INSUFFICIENT_FUNDS,
        payment_method="upi",
        customer_segment="REGULAR",
        downtime_severity="none",
        amount_log1p=10.0,
        customer_tenure_days=120.0,
        successful_payments_90d=5,
        failed_payments_30d=1,
        payment_success_rate_90d=0.83,
        historical_recovery_rate=0.5,
        lifetime_value_log1p=12.0,
        hours_since_failure=4.0,
        retry_count_provider=None,
        recovery_attempts_so_far=0,
        contacts_last_24h=0,
        rail_degraded=False,
        same_method_recent_success=True,
        alternate_method_recent_success=False,
        is_subscription=False,
        subscription_status=None,
        provider_retries_active=False,
        uncertain_provider_state=False,
        payment_link_data_sufficient=False,
        bounded_noise=0.0,
    )
    return replace(base, **overrides)


def test_same_seed_produces_identical_dataset_and_summary(tmp_path: Path) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first = generate_dataset(case_count=120, seed=DEFAULT_SEED)
    second = generate_dataset(case_count=120, seed=DEFAULT_SEED)
    write_dataset(first_dir, first)
    write_dataset(second_dir, second)
    assert _hash_file(first_dir / "training_data.csv") == _hash_file(
        second_dir / "training_data.csv"
    )
    assert _hash_file(first_dir / "summary.json") == _hash_file(second_dir / "summary.json")


def test_different_seed_changes_dataset(tmp_path: Path) -> None:
    first = generate_dataset(case_count=120, seed=DEFAULT_SEED)
    second = generate_dataset(case_count=120, seed=DEFAULT_SEED + 1)
    write_dataset(tmp_path / "a", first)
    write_dataset(tmp_path / "b", second)
    assert _hash_file(tmp_path / "a" / "training_data.csv") != _hash_file(
        tmp_path / "b" / "training_data.csv"
    )


def test_deterministic_case_ids() -> None:
    first = deterministic_case_id(dataset_version=DATASET_VERSION, seed=DEFAULT_SEED, case_index=7)
    second = deterministic_case_id(dataset_version=DATASET_VERSION, seed=DEFAULT_SEED, case_index=7)
    assert first == second


def test_deterministic_row_ordering() -> None:
    dataset = generate_dataset(case_count=50, seed=DEFAULT_SEED)
    keys = [(row["case_id"], row["action_type"]) for row in dataset.rows]
    assert keys == sorted(keys)


def test_no_duplicate_case_action_rows() -> None:
    dataset = generate_dataset(case_count=200, seed=DEFAULT_SEED)
    keys = [(row["case_id"], row["action_type"]) for row in dataset.rows]
    assert len(keys) == len(set(keys))


def test_requested_case_count_and_row_shape(tmp_path: Path) -> None:
    dataset = generate_dataset(case_count=180, seed=DEFAULT_SEED)
    write_dataset(tmp_path, dataset)
    rows = read_csv_rows(tmp_path / "training_data.csv")
    case_ids = {row["case_id"] for row in rows}
    assert len(case_ids) == 180
    per_case = Counter(row["case_id"] for row in rows)
    assert all(3 <= count <= 6 for count in per_case.values())


def test_csv_header_has_no_duplicate_columns(tmp_path: Path) -> None:
    dataset = generate_dataset(case_count=50, seed=DEFAULT_SEED)
    write_dataset(tmp_path, dataset)
    header = _read_csv_header(tmp_path / "training_data.csv")

    assert header == list(CSV_COLUMNS)
    assert len(header) == len(set(header))
    assert header.count("action_type") == 1
    assert len(FEATURE_COLUMNS) == len(set(FEATURE_COLUMNS))
    assert CSV_COLUMNS.count("action_type") == 1
    assert FEATURE_COLUMNS.count("action_type") == 1


def test_count_feature_types_are_integers() -> None:
    case_rng = random.Random(DEFAULT_SEED)
    noise_rng = random.Random(DEFAULT_SEED + 1)
    case = generate_case_features(
        case_index=0,
        split="train",
        case_rng=case_rng,
        noise_rng=noise_rng,
        dataset_version=DATASET_VERSION,
        seed=DEFAULT_SEED,
    )

    assert isinstance(case.recovery_attempts_so_far, int)
    assert isinstance(case.contacts_last_24h, int)
    assert case.recovery_attempts_so_far >= 0
    assert case.contacts_last_24h >= 0

    if case.successful_payments_90d is not None:
        assert isinstance(case.successful_payments_90d, int)
        assert case.successful_payments_90d >= 0
    if case.failed_payments_30d is not None:
        assert isinstance(case.failed_payments_30d, int)
        assert case.failed_payments_30d >= 0
    if case.retry_count_provider is not None:
        assert isinstance(case.retry_count_provider, int)
        assert case.retry_count_provider >= 0

    dataset = generate_dataset(case_count=120, seed=DEFAULT_SEED)
    for row in dataset.rows:
        assert isinstance(row["recovery_attempts_so_far"], int)
        assert isinstance(row["contacts_last_24h"], int)
        assert row["recovery_attempts_so_far"] >= 0
        assert row["contacts_last_24h"] >= 0

        successes = row["successful_payments_90d"]
        if successes is not None:
            assert isinstance(successes, int)
            assert successes >= 0

        failures = row["failed_payments_30d"]
        if failures is not None:
            assert isinstance(failures, int)
            assert failures >= 0

        retry_count = row["retry_count_provider"]
        if retry_count is not None:
            assert isinstance(retry_count, int)
            assert retry_count >= 0


def test_default_split_seed_recorded_in_summary() -> None:
    dataset = generate_dataset(case_count=80, seed=DEFAULT_SEED)
    assert dataset.summary["split_seed"] == effective_split_seed(
        seed=DEFAULT_SEED,
        split_seed=None,
    )
    assert dataset.summary["split_seed"] == DEFAULT_SEED + 3


def _unique_case_rows(rows: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique_rows: list[dict] = []
    for row in rows:
        case_id = row["case_id"]
        if case_id in seen:
            continue
        seen.add(case_id)
        unique_rows.append(row)
    return unique_rows


def _rail_degraded_value(row: dict) -> bool:
    value = row["rail_degraded"]
    if isinstance(value, bool):
        return value
    return str(value).lower() == "true"


def test_downtime_normalization_invariant_full_default_sample() -> None:
    dataset = generate_dataset(case_count=15_000, seed=DEFAULT_SEED)
    unique_rows = _unique_case_rows(dataset.rows)

    rail_without_downtime = 0
    downtime_without_rail = 0
    subscription_downtime_cases = 0

    for row in unique_rows:
        rail_degraded = _rail_degraded_value(row)
        failure_category = row["failure_category"]

        if rail_degraded:
            assert failure_category == FailureCategory.PAYMENT_RAIL_DOWNTIME.value
            if row["is_subscription"] in (True, "true"):
                subscription_downtime_cases += 1
        else:
            assert failure_category != FailureCategory.PAYMENT_RAIL_DOWNTIME.value

        if failure_category == FailureCategory.PAYMENT_RAIL_DOWNTIME.value:
            assert rail_degraded is True
        if rail_degraded and failure_category != FailureCategory.PAYMENT_RAIL_DOWNTIME.value:
            rail_without_downtime += 1
        if failure_category == FailureCategory.PAYMENT_RAIL_DOWNTIME.value and not rail_degraded:
            downtime_without_rail += 1

    assert rail_without_downtime == 0
    assert downtime_without_rail == 0
    assert subscription_downtime_cases > 0


def test_downtime_normalization_invariant_on_deterministic_sample() -> None:
    dataset = generate_dataset(case_count=2_000, seed=DEFAULT_SEED)
    for row in _unique_case_rows(dataset.rows):
        rail_degraded = _rail_degraded_value(row)
        failure_category = row["failure_category"]
        if rail_degraded:
            assert failure_category == FailureCategory.PAYMENT_RAIL_DOWNTIME.value
        if failure_category == FailureCategory.PAYMENT_RAIL_DOWNTIME.value:
            assert rail_degraded is True


def test_subscription_active_downtime_produces_production_candidates() -> None:
    context = CandidateGenerationContext(
        failure_category=FailureCategory.PAYMENT_RAIL_DOWNTIME,
        case_type=CaseType.SUBSCRIPTION_FAILURE,
        subscription_status="pending",
        provider_retries_active=True,
        active_payment_rail_downtime=True,
    )
    case = _case_for_context(context)
    ctx = candidate_context_from_case(case)
    produced = tuple(action.value for action in generate_candidates(ctx))
    expected = tuple(action.value for action in generate_candidates(context))
    assert produced == expected


def test_payment_history_coherence_direct_sampler() -> None:
    rng = random.Random(DEFAULT_SEED)
    for _ in range(500):
        history = _sample_payment_history(rng, segment="REGULAR", allow_missing=False)
        assert isinstance(history, SyntheticPaymentHistory)

        if history.successes_90d is None:
            assert history.failures_90d is None
            assert history.failed_payments_30d is None
            continue

        assert isinstance(history.successes_90d, int)
        assert isinstance(history.failures_90d, int)
        assert history.successes_90d >= 0
        assert history.failures_90d >= 0

        if history.failed_payments_30d is not None:
            assert isinstance(history.failed_payments_30d, int)
            assert history.failed_payments_30d >= 0
            assert history.failed_payments_30d <= history.failures_90d

        attempts = history.attempts_90d
        assert attempts is not None
        assert history.successes_90d + history.failures_90d == attempts

        if attempts > 0:
            assert history.payment_success_rate_90d == history.successes_90d / attempts
        else:
            assert history.payment_success_rate_90d is None


def test_payment_history_coherence_in_generated_dataset() -> None:
    dataset = generate_dataset(case_count=500, seed=DEFAULT_SEED)
    for row in _unique_case_rows(dataset.rows):
        successes = row["successful_payments_90d"]
        failures_30d = row["failed_payments_30d"]
        rate = row["payment_success_rate_90d"]

        if successes is None:
            continue

        assert isinstance(successes, int)
        assert successes >= 0
        if failures_30d is not None:
            assert isinstance(failures_30d, int)
            assert failures_30d >= 0

        if rate not in ("", None):
            assert 0.0 <= float(rate) <= 1.0


def test_customer_abandonment_candidate_generation_matches_production() -> None:
    context = CandidateGenerationContext(
        failure_category=FailureCategory.CUSTOMER_ABANDONMENT,
        case_type=CaseType.PAYMENT_FAILURE,
    )
    case = _case_for_context(context)
    ctx = candidate_context_from_case(case)
    produced = tuple(action.value for action in generate_candidates(ctx))
    expected = tuple(action.value for action in generate_candidates(context))
    assert produced == expected


def test_customer_abandonment_occurs_in_synthetic_sample() -> None:
    dataset = generate_dataset(case_count=5_000, seed=DEFAULT_SEED)
    categories = {
        row["failure_category"] for row in _unique_case_rows(dataset.rows)
    }
    assert FailureCategory.CUSTOMER_ABANDONMENT.value in categories


def test_split_seed_changes_only_split_assignment() -> None:
    dataset_a = generate_dataset(case_count=120, seed=DEFAULT_SEED, split_seed=100)
    dataset_b = generate_dataset(case_count=120, seed=DEFAULT_SEED, split_seed=200)

    assert dataset_a.summary["split_seed"] == 100
    assert dataset_b.summary["split_seed"] == 200

    rows_a = [_row_without_split(row) for row in dataset_a.rows]
    rows_b = [_row_without_split(row) for row in dataset_b.rows]
    assert rows_a == rows_b

    splits_a = {row["case_id"]: row["split"] for row in dataset_a.rows}
    splits_b = {row["case_id"]: row["split"] for row in dataset_b.rows}
    assert splits_a.keys() == splits_b.keys()
    assert splits_a != splits_b


def test_labels_latent_and_stop_behavior() -> None:
    dataset = generate_dataset(case_count=100, seed=DEFAULT_SEED)
    for row in dataset.rows:
        assert row["recovered_within_72h"] in (0, 1)
        latent = float(row["synthetic_latent_probability"])
        assert 0.0 <= latent <= 1.0
        if row["action_type"] == RecoveryActionType.STOP.value:
            assert latent == 0.0
            assert row["recovered_within_72h"] == 0


def test_feature_schema_and_forbidden_columns() -> None:
    dataset = generate_dataset(case_count=80, seed=DEFAULT_SEED)
    assert dataset.summary["feature_schema_version"] == FEATURE_SCHEMA_VERSION
    assert set(dataset.summary["feature_columns"]) == set(FEATURE_COLUMNS)
    assert FORBIDDEN_FEATURE_COLUMNS.isdisjoint(set(FEATURE_COLUMNS))


def test_group_split_has_no_case_leakage() -> None:
    dataset = generate_dataset(case_count=300, seed=DEFAULT_SEED)
    case_splits: dict[str, set[str]] = {}
    for row in dataset.rows:
        case_splits.setdefault(row["case_id"], set()).add(row["split"])
    assert all(len(splits) == 1 for splits in case_splits.values())

    train_cases = {cid for cid, splits in case_splits.items() if "train" in splits}
    valid_cases = {cid for cid, splits in case_splits.items() if "validation" in splits}
    test_cases = {cid for cid, splits in case_splits.items() if "test" in splits}
    assert train_cases.isdisjoint(valid_cases)
    assert train_cases.isdisjoint(test_cases)
    assert valid_cases.isdisjoint(test_cases)

    summary = dataset.summary
    total_cases = summary["case_count"]
    assert summary["split_case_counts"]["train"] == int(total_cases * 0.70)
    assert summary["split_case_counts"]["validation"] == int(total_cases * 0.15)
    assert summary["split_case_counts"]["test"] == total_cases - int(total_cases * 0.70) - int(
        total_cases * 0.15
    )


def test_case_features_independent_of_label_sampling_rng() -> None:
    case_rng = random.Random(DEFAULT_SEED)
    noise_rng = random.Random(DEFAULT_SEED + 1)
    case_a = generate_case_features(
        case_index=0,
        split="train",
        case_rng=case_rng,
        noise_rng=noise_rng,
        dataset_version=DATASET_VERSION,
        seed=DEFAULT_SEED,
    )
    case_rng = random.Random(DEFAULT_SEED)
    noise_rng = random.Random(DEFAULT_SEED + 1)
    case_b = generate_case_features(
        case_index=0,
        split="train",
        case_rng=case_rng,
        noise_rng=noise_rng,
        dataset_version=DATASET_VERSION,
        seed=DEFAULT_SEED,
    )
    assert case_a == case_b

    context = candidate_context_from_case(case_a)
    actions = generate_candidates(context)
    action = actions[0]
    latent = compute_latent_probability(case_a, action)
    label_a = 1 if random.Random(100).random() < latent else 0
    label_b = 1 if random.Random(200).random() < latent else 0
    assert case_a.amount_log1p == case_b.amount_log1p
    assert latent == compute_latent_probability(case_b, action)
    assert label_a in (0, 1) and label_b in (0, 1)


@pytest.mark.parametrize(
    ("context",),
    [
        (
            CandidateGenerationContext(
                failure_category=FailureCategory.PAYMENT_RAIL_DOWNTIME,
                case_type=CaseType.PAYMENT_FAILURE,
                active_payment_rail_downtime=True,
            ),
        ),
        (
            CandidateGenerationContext(
                failure_category=FailureCategory.INSUFFICIENT_FUNDS,
                case_type=CaseType.PAYMENT_FAILURE,
            ),
        ),
        (
            CandidateGenerationContext(
                failure_category=FailureCategory.AUTHENTICATION_FAILURE,
                case_type=CaseType.PAYMENT_FAILURE,
            ),
        ),
        (
            CandidateGenerationContext(
                failure_category=FailureCategory.BANK_OR_ISSUER_DECLINE,
                case_type=CaseType.PAYMENT_FAILURE,
            ),
        ),
        (
            CandidateGenerationContext(
                failure_category=FailureCategory.EXPIRED_OR_INVALID_METHOD,
                case_type=CaseType.PAYMENT_FAILURE,
            ),
        ),
        (
            CandidateGenerationContext(
                failure_category=FailureCategory.TECHNICAL_FAILURE,
                case_type=CaseType.PAYMENT_FAILURE,
            ),
        ),
        (
            CandidateGenerationContext(
                failure_category=FailureCategory.UNKNOWN,
                case_type=CaseType.PAYMENT_FAILURE,
                payment_link_data_sufficient=True,
            ),
        ),
        (
            CandidateGenerationContext(
                failure_category=FailureCategory.CUSTOMER_ABANDONMENT,
                case_type=CaseType.PAYMENT_FAILURE,
            ),
        ),
        (
            CandidateGenerationContext(
                failure_category=FailureCategory.MANDATE_OR_RECURRING_FAILURE,
                case_type=CaseType.SUBSCRIPTION_FAILURE,
                subscription_status="pending",
                provider_retries_active=True,
            ),
        ),
        (
            CandidateGenerationContext(
                failure_category=FailureCategory.MANDATE_OR_RECURRING_FAILURE,
                case_type=CaseType.SUBSCRIPTION_FAILURE,
                subscription_status="halted",
            ),
        ),
        (
            CandidateGenerationContext(
                failure_category=FailureCategory.MANDATE_OR_RECURRING_FAILURE,
                case_type=CaseType.SUBSCRIPTION_FAILURE,
                subscription_status="active",
            ),
        ),
    ],
)
def test_generated_actions_match_production_candidate_generator(
    context: CandidateGenerationContext,
) -> None:
    case = _case_for_context(context)
    ctx = candidate_context_from_case(case)
    produced = tuple(action.value for action in generate_candidates(ctx))
    expected = tuple(action.value for action in generate_candidates(context))
    assert produced == expected


def _case_for_context(context: CandidateGenerationContext) -> SyntheticCaseFeatures:
    return _base_case(
        case_type=context.case_type,
        failure_category=context.failure_category,
        is_subscription=context.case_type == CaseType.SUBSCRIPTION_FAILURE,
        subscription_status=context.subscription_status,
        provider_retries_active=context.provider_retries_active,
        uncertain_provider_state=context.uncertain_provider_state,
        rail_degraded=context.active_payment_rail_downtime,
        payment_link_data_sufficient=context.payment_link_data_sufficient,
        downtime_severity="high" if context.active_payment_rail_downtime else "none",
    )


def test_downtime_latent_probability_prefers_alternate_over_retry() -> None:
    case = _base_case(
        failure_category=FailureCategory.PAYMENT_RAIL_DOWNTIME,
        rail_degraded=True,
        downtime_severity="high",
    )
    retry_p = compute_latent_probability(case, RecoveryActionType.RETRY_SAME_METHOD)
    alternate_p = compute_latent_probability(
        case,
        RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD,
    )
    assert alternate_p > retry_p


def test_expired_method_latent_probability_prefers_alternate_over_retry() -> None:
    case = _base_case(failure_category=FailureCategory.EXPIRED_OR_INVALID_METHOD)
    retry_p = compute_latent_probability(case, RecoveryActionType.RETRY_SAME_METHOD)
    alternate_p = compute_latent_probability(
        case,
        RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD,
    )
    link_p = compute_latent_probability(case, RecoveryActionType.CREATE_PAYMENT_LINK)
    assert alternate_p > retry_p
    assert link_p > retry_p


def test_contact_and_attempt_fatigue_reduce_probability() -> None:
    base = _base_case()
    low_contacts = compute_latent_probability(
        base,
        RecoveryActionType.SEND_RECOVERY_MESSAGE,
    )
    high_contacts = compute_latent_probability(
        _base_case(contacts_last_24h=4),
        RecoveryActionType.SEND_RECOVERY_MESSAGE,
    )
    assert high_contacts < low_contacts

    low_attempts = compute_latent_probability(base, RecoveryActionType.CREATE_PAYMENT_LINK)
    high_attempts = compute_latent_probability(
        _base_case(recovery_attempts_so_far=3),
        RecoveryActionType.CREATE_PAYMENT_LINK,
    )
    assert high_attempts < low_attempts


def test_strong_payment_history_increases_probability() -> None:
    weak = _base_case(
        payment_success_rate_90d=0.10,
        same_method_recent_success=False,
        alternate_method_recent_success=False,
    )
    strong = _base_case(
        payment_success_rate_90d=0.90,
        same_method_recent_success=True,
        alternate_method_recent_success=True,
    )
    action = RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD
    assert compute_latent_probability(strong, action) > compute_latent_probability(weak, action)


def test_action_conditional_latent_probabilities_differ_for_same_case() -> None:
    case = _base_case(failure_category=FailureCategory.AUTHENTICATION_FAILURE)
    context = candidate_context_from_case(case)
    actions = [
        action for action in generate_candidates(context) if action != RecoveryActionType.STOP
    ]
    probabilities = {action: compute_latent_probability(case, action) for action in actions}
    assert len(set(probabilities.values())) >= 2


def test_multiple_non_stop_actions_can_be_latent_best() -> None:
    dataset = generate_dataset(case_count=500, seed=DEFAULT_SEED)
    best_actions = dataset.summary["latent_best_action_distribution"]
    assert len(best_actions) >= 2


def test_internal_feature_coherence() -> None:
    dataset = generate_dataset(case_count=250, seed=DEFAULT_SEED)
    for row in dataset.rows:
        rate_value = row["payment_success_rate_90d"]
        if rate_value not in ("", None):
            rate = float(rate_value)
            assert 0.0 <= rate <= 1.0
        hist_value = row["historical_recovery_rate"]
        if hist_value not in ("", None):
            rate = float(hist_value)
            assert 0.0 <= rate <= 1.0
        assert float(row["amount_log1p"]) >= 0.0
        assert float(row["lifetime_value_log1p"]) >= 0.0
        assert float(row["customer_tenure_days"]) >= 0.0
        assert int(row["recovery_attempts_so_far"]) >= 0
        assert int(row["contacts_last_24h"]) >= 0


def test_cli_invalid_cases_rejected() -> None:
    from ml.generate_training_data import main

    with pytest.raises(SystemExit):
        main(["--cases", "0"])
