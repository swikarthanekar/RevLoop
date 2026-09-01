"""Shared constants and logic for synthetic recovery ML dataset generation."""

from __future__ import annotations

import csv
import json
import math
import random
import uuid
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.domain.enums import CaseType, FailureCategory, RecoveryActionType
from app.recovery.candidates import generate_candidates
from app.recovery.schemas import FEATURE_SCHEMA_VERSION, CandidateGenerationContext

DATASET_VERSION = "synthetic_recovery_v1"
DEFAULT_SEED = 20260901
DEFAULT_CASE_COUNT = 15_000

TRAIN_FRACTION = 0.70
VALIDATION_FRACTION = 0.15
TEST_FRACTION = 0.15

SYNTHETIC_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

PAYMENT_METHODS = ("upi", "card", "netbanking", "wallet")
CUSTOMER_SEGMENTS = ("REGULAR", "HIGH_VALUE", "VIP", "NEW")
DOWNTIME_SEVERITIES = ("none", "unknown", "low", "medium", "high")

PAYMENT_FAILURE_CATEGORIES: tuple[FailureCategory, ...] = (
    FailureCategory.INSUFFICIENT_FUNDS,
    FailureCategory.AUTHENTICATION_FAILURE,
    FailureCategory.BANK_OR_ISSUER_DECLINE,
    FailureCategory.EXPIRED_OR_INVALID_METHOD,
    FailureCategory.TECHNICAL_FAILURE,
    FailureCategory.UNKNOWN,
    FailureCategory.CUSTOMER_ABANDONMENT,
)

PAYMENT_FAILURE_CATEGORY_WEIGHTS: tuple[float, ...] = (
    0.22,
    0.12,
    0.16,
    0.10,
    0.12,
    0.10,
    0.08,
)

NUMERICAL_FEATURE_COLUMNS: tuple[str, ...] = (
    "amount_log1p",
    "customer_tenure_days",
    "successful_payments_90d",
    "failed_payments_30d",
    "payment_success_rate_90d",
    "historical_recovery_rate",
    "lifetime_value_log1p",
    "hours_since_failure",
    "retry_count_provider",
    "recovery_attempts_so_far",
    "contacts_last_24h",
)

BOOLEAN_FEATURE_COLUMNS: tuple[str, ...] = (
    "rail_degraded",
    "same_method_recent_success",
    "alternate_method_recent_success",
    "is_subscription",
)

CATEGORICAL_FEATURE_COLUMNS: tuple[str, ...] = (
    "case_type",
    "failure_category",
    "payment_method",
    "customer_segment",
    "downtime_severity",
    "action_type",
)

FEATURE_COLUMNS: tuple[str, ...] = (
    *NUMERICAL_FEATURE_COLUMNS,
    *BOOLEAN_FEATURE_COLUMNS,
    *CATEGORICAL_FEATURE_COLUMNS,
)

METADATA_COLUMNS: tuple[str, ...] = (
    "case_id",
    "split",
    "recovered_within_72h",
    "synthetic_latent_probability",
)

FORBIDDEN_FEATURE_COLUMNS: frozenset[str] = frozenset(
    {
        "recovered_within_72h",
        "synthetic_latent_probability",
        "recovered_amount",
        "expected_recovered",
        "expected_value",
        "erv",
        "confidence",
        "policy_eligible",
        "requires_approval",
        "recommendation_rank",
        "action_status",
        "action_result",
        "final_case_status",
        "outcome",
        "case_id",
        "split",
    }
)

CSV_COLUMNS: tuple[str, ...] = (
    "case_id",
    "split",
    "recovered_within_72h",
    "synthetic_latent_probability",
    *FEATURE_COLUMNS,
)

# ---------------------------------------------------------------------------
# SYNTHETIC SIMULATION ASSUMPTIONS
# Centralized hidden outcome mechanism coefficients — not trained on real data.
# ---------------------------------------------------------------------------

GLOBAL_INTERCEPT = -1.35

ACTION_BIAS: dict[RecoveryActionType, float] = {
    RecoveryActionType.WAIT: -0.15,
    RecoveryActionType.RETRY_SAME_METHOD: -0.05,
    RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD: 0.20,
    RecoveryActionType.CREATE_PAYMENT_LINK: 0.25,
    RecoveryActionType.SEND_RECOVERY_MESSAGE: 0.05,
    RecoveryActionType.ESCALATE_TO_HUMAN: -0.10,
    RecoveryActionType.STOP: -10.0,
}

FAILURE_ACTION_INTERACTION: dict[tuple[FailureCategory, RecoveryActionType], float] = {
    (FailureCategory.PAYMENT_RAIL_DOWNTIME, RecoveryActionType.RETRY_SAME_METHOD): -1.80,
    (
        FailureCategory.PAYMENT_RAIL_DOWNTIME,
        RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD,
    ): 0.90,
    (FailureCategory.PAYMENT_RAIL_DOWNTIME, RecoveryActionType.CREATE_PAYMENT_LINK): 0.55,
    (FailureCategory.PAYMENT_RAIL_DOWNTIME, RecoveryActionType.WAIT): 0.35,
    (FailureCategory.EXPIRED_OR_INVALID_METHOD, RecoveryActionType.RETRY_SAME_METHOD): -1.60,
    (
        FailureCategory.EXPIRED_OR_INVALID_METHOD,
        RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD,
    ): 1.10,
    (FailureCategory.EXPIRED_OR_INVALID_METHOD, RecoveryActionType.CREATE_PAYMENT_LINK): 1.00,
    (FailureCategory.INSUFFICIENT_FUNDS, RecoveryActionType.SEND_RECOVERY_MESSAGE): 0.45,
    (FailureCategory.INSUFFICIENT_FUNDS, RecoveryActionType.CREATE_PAYMENT_LINK): 0.35,
    (FailureCategory.AUTHENTICATION_FAILURE, RecoveryActionType.RETRY_SAME_METHOD): 0.55,
    (FailureCategory.BANK_OR_ISSUER_DECLINE, RecoveryActionType.WAIT): 0.20,
    (FailureCategory.MANDATE_OR_RECURRING_FAILURE, RecoveryActionType.WAIT): 0.25,
    (FailureCategory.UNKNOWN, RecoveryActionType.ESCALATE_TO_HUMAN): 0.15,
}

METHOD_ACTION_INTERACTION: dict[tuple[str, RecoveryActionType], float] = {
    ("upi", RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD): 0.15,
    ("card", RecoveryActionType.RETRY_SAME_METHOD): 0.10,
    ("netbanking", RecoveryActionType.CREATE_PAYMENT_LINK): 0.12,
    ("wallet", RecoveryActionType.SEND_RECOVERY_MESSAGE): 0.08,
}

COEFF_PRIOR_SUCCESS_RATE = 1.40
COEFF_SAME_METHOD_SUCCESS = 0.75
COEFF_ALTERNATE_METHOD_SUCCESS = 0.55
COEFF_CONTACTS_LAST_24H = 0.35
COEFF_RECOVERY_ATTEMPTS = 0.45
COEFF_CUSTOMER_TENURE = 0.18
COEFF_LIFETIME_VALUE_LOG = 0.12
COEFF_RAIL_DEGRADED = -0.65
BOUNDED_NOISE_MIN = -0.08
BOUNDED_NOISE_MAX = 0.08
ACTIVE_DOWNTIME_PROBABILITY = 0.08
FAILURES_IN_30D_GIVEN_90D_FAILURE_PROBABILITY = 0.35


@dataclass(frozen=True)
class SyntheticPaymentHistory:
    """Internal payment-history snapshot used during synthetic case generation."""

    successes_90d: int | None
    failures_90d: int | None
    failed_payments_30d: int | None
    payment_success_rate_90d: float | None
    same_method_recent_success: bool
    alternate_method_recent_success: bool

    @property
    def attempts_90d(self) -> int | None:
        if self.successes_90d is None or self.failures_90d is None:
            return None
        return self.successes_90d + self.failures_90d


@dataclass(frozen=True)
class SyntheticCaseFeatures:
    case_index: int
    case_id: str
    split: str
    case_type: CaseType
    failure_category: FailureCategory
    payment_method: str
    customer_segment: str
    downtime_severity: str
    amount_log1p: float
    customer_tenure_days: float
    successful_payments_90d: int | None
    failed_payments_30d: int | None
    payment_success_rate_90d: float | None
    historical_recovery_rate: float | None
    lifetime_value_log1p: float
    hours_since_failure: float
    retry_count_provider: int | None
    recovery_attempts_so_far: int
    contacts_last_24h: int
    rail_degraded: bool
    same_method_recent_success: bool
    alternate_method_recent_success: bool
    is_subscription: bool
    subscription_status: str | None
    provider_retries_active: bool
    uncertain_provider_state: bool
    payment_link_data_sufficient: bool
    bounded_noise: float


@dataclass
class SyntheticDataset:
    rows: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


def deterministic_case_id(*, dataset_version: str, seed: int, case_index: int) -> str:
    name = f"{dataset_version}:{seed}:{case_index}"
    return str(uuid.uuid5(SYNTHETIC_NAMESPACE, name))


def _sigmoid(value: float) -> float:
    if value >= 0:
        exp = math.exp(-value)
        return 1.0 / (1.0 + exp)
    exp = math.exp(value)
    return exp / (1.0 + exp)


def compute_latent_probability(
    case: SyntheticCaseFeatures,
    action: RecoveryActionType,
) -> float:
    if action == RecoveryActionType.STOP:
        return 0.0

    logit = GLOBAL_INTERCEPT
    logit += ACTION_BIAS[action]
    logit += FAILURE_ACTION_INTERACTION.get((case.failure_category, action), 0.0)
    logit += METHOD_ACTION_INTERACTION.get((case.payment_method, action), 0.0)

    if case.payment_success_rate_90d is not None:
        logit += COEFF_PRIOR_SUCCESS_RATE * case.payment_success_rate_90d
    if case.same_method_recent_success:
        logit += COEFF_SAME_METHOD_SUCCESS
    if case.alternate_method_recent_success:
        logit += COEFF_ALTERNATE_METHOD_SUCCESS

    logit -= COEFF_CONTACTS_LAST_24H * case.contacts_last_24h
    logit -= COEFF_RECOVERY_ATTEMPTS * case.recovery_attempts_so_far
    logit += COEFF_CUSTOMER_TENURE * min(case.customer_tenure_days / 365.0, 1.0)
    logit += COEFF_LIFETIME_VALUE_LOG * min(case.lifetime_value_log1p / 15.0, 1.0)
    if case.rail_degraded:
        logit += COEFF_RAIL_DEGRADED

    logit += case.bounded_noise
    probability = _sigmoid(logit)
    return max(0.0, min(1.0, probability))


def candidate_context_from_case(case: SyntheticCaseFeatures) -> CandidateGenerationContext:
    return CandidateGenerationContext(
        failure_category=case.failure_category,
        case_type=case.case_type,
        subscription_status=case.subscription_status,
        provider_retries_active=case.provider_retries_active,
        uncertain_provider_state=case.uncertain_provider_state,
        active_payment_rail_downtime=case.rail_degraded,
        payment_link_data_sufficient=case.payment_link_data_sufficient,
    )


def _choose_weighted(rng: random.Random, items: Sequence[Any], weights: Sequence[float]) -> Any:
    return rng.choices(list(items), weights=list(weights), k=1)[0]


def _sample_payment_history(
    rng: random.Random,
    *,
    segment: str,
    allow_missing: bool,
) -> SyntheticPaymentHistory:
    if allow_missing and rng.random() < 0.08:
        return SyntheticPaymentHistory(
            successes_90d=None,
            failures_90d=None,
            failed_payments_30d=None,
            payment_success_rate_90d=None,
            same_method_recent_success=False,
            alternate_method_recent_success=False,
        )

    attempts_90d = rng.randint(0, 20)
    if segment in {"HIGH_VALUE", "VIP"}:
        attempts_90d += rng.randint(3, 12)
    elif segment == "NEW":
        attempts_90d = rng.randint(0, 4)

    successes_90d = rng.randint(0, attempts_90d) if attempts_90d > 0 else 0
    failures_90d = attempts_90d - successes_90d
    if failures_90d == 0:
        failed_payments_30d = 0
    else:
        failed_payments_30d = sum(
            1
            for _ in range(failures_90d)
            if rng.random() < FAILURES_IN_30D_GIVEN_90D_FAILURE_PROBABILITY
        )

    rate = successes_90d / attempts_90d if attempts_90d > 0 else None

    same_method = successes_90d > 0 and rng.random() < min(0.85, 0.35 + (rate or 0.0))
    alternate = (
        successes_90d > 0
        and not same_method
        and rng.random() < min(0.75, 0.25 + (rate or 0.0))
    ) or (successes_90d > 1 and rng.random() < 0.35)

    return SyntheticPaymentHistory(
        successes_90d=successes_90d,
        failures_90d=failures_90d,
        failed_payments_30d=failed_payments_30d,
        payment_success_rate_90d=rate,
        same_method_recent_success=same_method,
        alternate_method_recent_success=alternate,
    )


def generate_case_features(
    *,
    case_index: int,
    split: str,
    case_rng: random.Random,
    noise_rng: random.Random,
    dataset_version: str,
    seed: int,
) -> SyntheticCaseFeatures:
    is_subscription = case_rng.random() < 0.25
    case_type = CaseType.SUBSCRIPTION_FAILURE if is_subscription else CaseType.PAYMENT_FAILURE

    segment = _choose_weighted(case_rng, CUSTOMER_SEGMENTS, (0.55, 0.20, 0.10, 0.15))
    payment_method = _choose_weighted(case_rng, PAYMENT_METHODS, (0.45, 0.30, 0.15, 0.10))

    if is_subscription:
        underlying_failure_category = FailureCategory.MANDATE_OR_RECURRING_FAILURE
        subscription_status = _choose_weighted(
            case_rng,
            ("pending", "halted", "active"),
            (0.45, 0.20, 0.35),
        )
        provider_retries_active = subscription_status == "pending" and case_rng.random() < 0.80
        retry_count: int | None = case_rng.randint(0, 4)
        retry_missing = False
    else:
        underlying_failure_category = _choose_weighted(
            case_rng,
            PAYMENT_FAILURE_CATEGORIES,
            PAYMENT_FAILURE_CATEGORY_WEIGHTS,
        )
        subscription_status = None
        provider_retries_active = False
        retry_count = None
        retry_missing = True

    verified_active_downtime = case_rng.random() < ACTIVE_DOWNTIME_PROBABILITY
    if verified_active_downtime:
        failure_category = FailureCategory.PAYMENT_RAIL_DOWNTIME
        rail_degraded = True
        downtime_severity = _choose_weighted(
            case_rng,
            ("high", "medium", "low"),
            (0.45, 0.35, 0.20),
        )
    else:
        failure_category = underlying_failure_category
        rail_degraded = False
        downtime_severity = (
            "unknown" if failure_category == FailureCategory.UNKNOWN else "none"
        )

    amount_minor = case_rng.randint(5_000, 2_500_000)
    if segment in {"HIGH_VALUE", "VIP"}:
        amount_minor = case_rng.randint(250_000, 4_000_000)

    tenure_days = case_rng.uniform(7.0, 1200.0)
    if segment in {"HIGH_VALUE", "VIP"}:
        tenure_days = case_rng.uniform(180.0, 1800.0)
    elif segment == "NEW":
        tenure_days = case_rng.uniform(3.0, 120.0)

    ltv_minor = case_rng.randint(10_000, 5_000_000)
    if segment == "VIP":
        ltv_minor = case_rng.randint(1_000_000, 12_000_000)
    elif segment == "HIGH_VALUE":
        ltv_minor = case_rng.randint(500_000, 6_000_000)
    elif segment == "NEW":
        ltv_minor = case_rng.randint(0, 250_000)

    payment_history = _sample_payment_history(
        case_rng,
        segment=segment,
        allow_missing=True,
    )

    hist_rate: float | None
    if segment == "NEW" and case_rng.random() < 0.55:
        hist_rate = None
    else:
        prior_total = case_rng.randint(0, 8)
        prior_recovered = case_rng.randint(0, prior_total) if prior_total else 0
        hist_rate = prior_recovered / prior_total if prior_total else None

    if is_subscription and case_rng.random() < 0.05:
        retry_count = None
        retry_missing = True

    recovery_attempts = case_rng.randint(0, 4)
    contacts = case_rng.randint(0, 4)
    uncertain = case_rng.random() < 0.03
    payment_link_ok = case_rng.random() < 0.70

    bounded_noise = noise_rng.uniform(BOUNDED_NOISE_MIN, BOUNDED_NOISE_MAX)

    return SyntheticCaseFeatures(
        case_index=case_index,
        case_id=deterministic_case_id(
            dataset_version=dataset_version,
            seed=seed,
            case_index=case_index,
        ),
        split=split,
        case_type=case_type,
        failure_category=failure_category,
        payment_method=payment_method,
        customer_segment=segment,
        downtime_severity=downtime_severity,
        amount_log1p=math.log1p(amount_minor),
        customer_tenure_days=tenure_days,
        successful_payments_90d=payment_history.successes_90d,
        failed_payments_30d=payment_history.failed_payments_30d,
        payment_success_rate_90d=payment_history.payment_success_rate_90d,
        historical_recovery_rate=hist_rate,
        lifetime_value_log1p=math.log1p(ltv_minor),
        hours_since_failure=case_rng.uniform(0.5, 96.0),
        retry_count_provider=None if retry_missing else retry_count,
        recovery_attempts_so_far=recovery_attempts,
        contacts_last_24h=contacts,
        rail_degraded=rail_degraded,
        same_method_recent_success=payment_history.same_method_recent_success,
        alternate_method_recent_success=payment_history.alternate_method_recent_success,
        is_subscription=is_subscription,
        subscription_status=subscription_status,
        provider_retries_active=provider_retries_active,
        uncertain_provider_state=uncertain,
        payment_link_data_sufficient=payment_link_ok,
        bounded_noise=bounded_noise,
    )


def _feature_values(case: SyntheticCaseFeatures, action: RecoveryActionType) -> dict[str, Any]:
    return {
        "amount_log1p": case.amount_log1p,
        "customer_tenure_days": case.customer_tenure_days,
        "successful_payments_90d": case.successful_payments_90d,
        "failed_payments_30d": case.failed_payments_30d,
        "payment_success_rate_90d": case.payment_success_rate_90d,
        "historical_recovery_rate": case.historical_recovery_rate,
        "lifetime_value_log1p": case.lifetime_value_log1p,
        "hours_since_failure": case.hours_since_failure,
        "retry_count_provider": case.retry_count_provider,
        "recovery_attempts_so_far": case.recovery_attempts_so_far,
        "contacts_last_24h": case.contacts_last_24h,
        "rail_degraded": case.rail_degraded,
        "same_method_recent_success": case.same_method_recent_success,
        "alternate_method_recent_success": case.alternate_method_recent_success,
        "is_subscription": case.is_subscription,
        "case_type": case.case_type.value,
        "failure_category": case.failure_category.value,
        "payment_method": case.payment_method,
        "customer_segment": case.customer_segment,
        "downtime_severity": case.downtime_severity,
        "action_type": action.value,
    }


def _serialize_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return format(value, ".10g")
    return str(value)


def effective_split_seed(*, seed: int, split_seed: int | None) -> int:
    return split_seed if split_seed is not None else seed + 3


def assign_splits(case_ids: Sequence[str], *, split_rng: random.Random) -> dict[str, str]:
    ordered = list(case_ids)
    split_rng.shuffle(ordered)
    total = len(ordered)
    train_end = int(total * TRAIN_FRACTION)
    valid_end = train_end + int(total * VALIDATION_FRACTION)
    mapping: dict[str, str] = {}
    for index, case_id in enumerate(ordered):
        if index < train_end:
            mapping[case_id] = "train"
        elif index < valid_end:
            mapping[case_id] = "validation"
        else:
            mapping[case_id] = "test"
    return mapping


def generate_dataset(
    *,
    case_count: int,
    seed: int = DEFAULT_SEED,
    split_seed: int | None = None,
    dataset_version: str = DATASET_VERSION,
) -> SyntheticDataset:
    if case_count <= 0:
        raise ValueError("case_count must be > 0")

    resolved_split_seed = effective_split_seed(seed=seed, split_seed=split_seed)

    case_rng = random.Random(seed)
    noise_rng = random.Random(seed + 1)
    label_rng = random.Random(seed + 2)
    split_rng = random.Random(resolved_split_seed)

    case_ids = [
        deterministic_case_id(dataset_version=dataset_version, seed=seed, case_index=index)
        for index in range(case_count)
    ]
    split_map = assign_splits(case_ids, split_rng=split_rng)

    rows: list[dict[str, Any]] = []
    cases: list[SyntheticCaseFeatures] = []

    for case_index in range(case_count):
        case = generate_case_features(
            case_index=case_index,
            split=split_map[case_ids[case_index]],
            case_rng=case_rng,
            noise_rng=noise_rng,
            dataset_version=dataset_version,
            seed=seed,
        )
        cases.append(case)

        context = candidate_context_from_case(case)
        actions = generate_candidates(context)

        for action in actions:
            if action == RecoveryActionType.STOP:
                latent = 0.0
                label = 0
            else:
                latent = compute_latent_probability(case, action)
                label = 1 if label_rng.random() < latent else 0

            row = {
                "case_id": case.case_id,
                "split": case.split,
                "recovered_within_72h": label,
                "synthetic_latent_probability": latent,
                **_feature_values(case, action),
            }
            rows.append(row)

    rows.sort(key=lambda row: (row["case_id"], row["action_type"]))
    summary = build_summary(
        rows,
        cases=cases,
        seed=seed,
        split_seed=resolved_split_seed,
        dataset_version=dataset_version,
    )
    return SyntheticDataset(rows=rows, summary=summary)


def build_summary(
    rows: Sequence[dict[str, Any]],
    *,
    cases: Sequence[SyntheticCaseFeatures],
    seed: int,
    split_seed: int,
    dataset_version: str,
) -> dict[str, Any]:
    case_count = len(cases)
    row_count = len(rows)
    rows_per_case = Counter()
    for row in rows:
        rows_per_case[row["case_id"]] += 1

    split_case_counts = Counter(case.split for case in cases)
    split_row_counts = Counter(row["split"] for row in rows)
    labels = [int(row["recovered_within_72h"]) for row in rows]
    positive_rate = sum(labels) / row_count if row_count else 0.0

    latent_values = [float(row["synthetic_latent_probability"]) for row in rows]
    action_counter = Counter(row["action_type"] for row in rows)
    failure_counter = Counter(case.failure_category.value for case in cases)

    best_actions: Counter[str] = Counter()
    for case in cases:
        context = candidate_context_from_case(case)
        actions = [
            action
            for action in generate_candidates(context)
            if action != RecoveryActionType.STOP
        ]
        if not actions:
            continue
        best_action = max(actions, key=lambda action: compute_latent_probability(case, action))
        best_actions[best_action.value] += 1

    return {
        "dataset_version": dataset_version,
        "seed": seed,
        "split_seed": split_seed,
        "case_count": case_count,
        "row_count": row_count,
        "candidate_rows_per_case": {
            "min": min(rows_per_case.values()) if rows_per_case else 0,
            "max": max(rows_per_case.values()) if rows_per_case else 0,
            "distribution": dict(sorted(Counter(rows_per_case.values()).items())),
        },
        "split_case_counts": dict(sorted(split_case_counts.items())),
        "split_row_counts": dict(sorted(split_row_counts.items())),
        "overall_positive_label_rate": positive_rate,
        "positive_label_rate_by_split": {
            split: (
                sum(int(row["recovered_within_72h"]) for row in rows if row["split"] == split)
                / max(1, sum(1 for row in rows if row["split"] == split))
            )
            for split in ("train", "validation", "test")
        },
        "case_type_distribution": dict(
            sorted(Counter(case.case_type.value for case in cases).items())
        ),
        "failure_category_distribution": dict(sorted(failure_counter.items())),
        "action_type_distribution": dict(sorted(action_counter.items())),
        "payment_method_distribution": dict(
            sorted(Counter(case.payment_method for case in cases).items())
        ),
        "customer_segment_distribution": dict(
            sorted(Counter(case.customer_segment for case in cases).items())
        ),
        "rail_degraded_distribution": dict(
            sorted(Counter(str(case.rail_degraded) for case in cases).items())
        ),
        "latent_probability_summary": {
            "min": min(latent_values) if latent_values else 0.0,
            "max": max(latent_values) if latent_values else 0.0,
            "mean": sum(latent_values) / len(latent_values) if latent_values else 0.0,
        },
        "latent_best_action_distribution": dict(sorted(best_actions.items())),
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_columns": list(FEATURE_COLUMNS),
        "target_column": "recovered_within_72h",
        "group_column": "case_id",
        "split_column": "split",
        "evaluation_only_columns": ["synthetic_latent_probability"],
        "label": "SYNTHETIC DATA / SIMULATION ONLY",
    }


def write_dataset(output_dir: Path, dataset: SyntheticDataset) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "training_data.csv"
    summary_path = output_dir / "summary.json"

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CSV_COLUMNS), lineterminator="\n")
        writer.writeheader()
        for row in dataset.rows:
            writer.writerow({column: _serialize_value(row.get(column)) for column in CSV_COLUMNS})

    summary_path.write_text(
        json.dumps(dataset.summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return csv_path, summary_path


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))
