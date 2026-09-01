#!/usr/bin/env python3
"""Evaluate trusted Logistic Regression baseline on held-out test data (Prompt 11)."""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

# TRUSTED LOCAL ARTIFACT ONLY — never load arbitrary external pickle/joblib files.


def _configure_import_paths() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    for path in (repo_root / "apps" / "api", repo_root / "scripts"):
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)


def load_trusted_bundle(artifact_path: Path) -> dict[str, Any]:
    if not artifact_path.is_file():
        raise FileNotFoundError(f"Trusted artifact not found: {artifact_path}")
    bundle = joblib.load(artifact_path)
    if not isinstance(bundle, dict) or "model" not in bundle or "metadata" not in bundle:
        raise ValueError("Artifact bundle must contain model and metadata.")
    return bundle


def synthetic_offline_evaluation_policy():
    from decimal import Decimal

    from app.domain.enums import RecoveryActionType
    from app.policies.schemas import MerchantPolicyConfig

    return MerchantPolicyConfig(
        auto_action_limit_minor=10_000_000_000,
        max_recovery_attempts=10,
        max_contacts_per_24h=10,
        minimum_auto_confidence=Decimal(0),
        cooldown_minutes=0,
        automation_enabled=True,
        allowed_action_types=frozenset(RecoveryActionType),
    )


def compute_feature_completeness(row: pd.Series) -> float:
    from ml.common import NUMERICAL_FEATURE_COLUMNS

    present = 0
    total = len(NUMERICAL_FEATURE_COLUMNS)
    for column in NUMERICAL_FEATURE_COLUMNS:
        value = row[column]
        if pd.notna(value):
            present += 1
    return present / total if total else 1.0


def build_recommendation_candidates(
    *,
    case_rows: pd.DataFrame,
    pipeline,
    amount_at_risk_minor: int,
    policy,
) -> list:
    from ml.common import is_stop_action, parse_boolean_token
    from ml.train_baseline import predict_positive_probabilities

    from app.domain.enums import RecoveryActionType
    from app.policies.engine import evaluate_policy
    from app.policies.schemas import PolicyEvaluationContext
    from app.recovery.confidence import calculate_confidence
    from app.recovery.erv import calculate_erv
    from app.recovery.ranking import OPERATIONAL_BURDEN
    from app.recovery.schemas import RecommendationCandidate

    non_stop_rows = case_rows.loc[~case_rows["action_type"].map(is_stop_action)]
    probability_by_action: dict[str, Decimal] = {}
    if len(non_stop_rows) > 0:
        predicted = predict_positive_probabilities(pipeline, non_stop_rows)
        for (_, row), probability in zip(non_stop_rows.iterrows(), predicted, strict=True):
            probability_by_action[str(row["action_type"])] = Decimal(str(probability))
    for action_value in case_rows["action_type"].map(str):
        if is_stop_action(action_value):
            probability_by_action[action_value] = Decimal(0)

    candidates: list[RecommendationCandidate] = []
    for _, row in case_rows.iterrows():
        action = RecoveryActionType(str(row["action_type"]))
        probability = probability_by_action[action.value]
        contacts = int(row["contacts_last_24h"])
        erv = calculate_erv(
            action=action,
            amount_at_risk_minor=amount_at_risk_minor,
            success_probability=probability,
            contacts_last_24h=contacts,
        )
        confidence = calculate_confidence(
            feature_completeness=compute_feature_completeness(row),
            success_probability=probability,
            evidence_strength=Decimal("0.50"),
        )
        policy_context = PolicyEvaluationContext(
            action_type=action,
            amount_at_risk_minor=amount_at_risk_minor,
            recovery_attempts_so_far=int(row["recovery_attempts_so_far"]),
            contacts_last_24h=contacts,
            confidence=confidence,
            expected_value_minor=erv.expected_value_minor,
            payment_link_data_sufficient=True,
            case_terminal=False,
            provider_success_known=False,
            verified_rail_downtime=parse_boolean_token(row["rail_degraded"]),
            equivalent_actions_in_flight=frozenset(),
            auto_execution_requested=False,
            cooldown_elapsed_minutes=999,
            provider_retries_active=False,
        )
        decision = evaluate_policy(policy_context, policy)
        candidates.append(
            RecommendationCandidate(
                action_type=action,
                success_probability=probability,
                expected_recovered_minor=erv.expected_recovered_minor,
                expected_value_minor=erv.expected_value_minor,
                confidence=confidence,
                eligible=decision.eligible,
                requires_approval=decision.requires_approval,
                policy_reasons=tuple(reason.value for reason in decision.reasons),
                operational_burden=OPERATIONAL_BURDEN[action],
            )
        )
    return candidates


def select_naive_baseline(candidates: list) -> Any | None:
    from app.domain.enums import RecoveryActionType

    eligible = [candidate for candidate in candidates if candidate.eligible]
    by_action = {candidate.action_type: candidate for candidate in eligible}
    for action in (
        RecoveryActionType.RETRY_SAME_METHOD,
        RecoveryActionType.WAIT,
        RecoveryActionType.STOP,
    ):
        if action in by_action:
            return by_action[action]
    return None


def evaluate_selected_action(
    *,
    selected,
    case_rows: pd.DataFrame,
    amount_at_risk_minor: int,
) -> dict[str, Any]:
    from ml.common import is_stop_action

    from app.recovery.erv import CONTACT_ACTION_TYPES, round_half_up

    if selected is None:
        return {
            "action_type": None,
            "expected_synthetic_recovered_minor": 0,
            "realized_synthetic_recovered_minor": 0,
            "recovered_within_72h": 0,
            "is_stop": False,
            "is_contact": False,
            "is_intervention": False,
        }

    action_value = selected.action_type.value
    action_row = case_rows.loc[case_rows["action_type"] == action_value].iloc[0]
    latent = Decimal(str(action_row["synthetic_latent_probability"]))
    expected = round_half_up(latent * Decimal(amount_at_risk_minor))
    label = int(action_row["recovered_within_72h"])
    realized = amount_at_risk_minor if label == 1 else 0
    is_stop = is_stop_action(action_value)
    is_contact = selected.action_type in CONTACT_ACTION_TYPES
    is_intervention = not is_stop
    return {
        "action_type": action_value,
        "expected_synthetic_recovered_minor": expected,
        "realized_synthetic_recovered_minor": realized,
        "recovered_within_72h": label,
        "is_stop": is_stop,
        "is_contact": is_contact,
        "is_intervention": is_intervention,
    }


def simulate_policy_on_test_cases(
    *,
    frame: pd.DataFrame,
    pipeline,
) -> dict[str, Any]:
    from ml.common import decode_amount_at_risk_minor
    from ml.train_baseline import predictive_frame, split_frame

    from app.recovery.ranking import rank_candidates, select_recommendation

    test_frame = split_frame(frame, split_name="test")
    predictive_test = predictive_frame(test_frame)
    policy = synthetic_offline_evaluation_policy()

    revloop_results: list[dict[str, Any]] = []
    naive_results: list[dict[str, Any]] = []

    for case_id, case_rows in predictive_test.groupby("case_id"):
        case_rows = case_rows.sort_values("action_type").copy()
        amount_log1p = float(case_rows.iloc[0]["amount_log1p"])
        amount_at_risk_minor = decode_amount_at_risk_minor(amount_log1p)

        stop_rows = test_frame.loc[
            (test_frame["case_id"] == case_id) & (test_frame["action_type"] == "STOP")
        ]
        all_case_rows = pd.concat([case_rows, stop_rows], ignore_index=True)

        candidates = build_recommendation_candidates(
            case_rows=all_case_rows,
            pipeline=pipeline,
            amount_at_risk_minor=amount_at_risk_minor,
            policy=policy,
        )
        ranked = rank_candidates(candidates)
        revloop_selected = select_recommendation(ranked)
        naive_selected = select_naive_baseline(candidates)

        revloop_results.append(
            evaluate_selected_action(
                selected=revloop_selected,
                case_rows=all_case_rows,
                amount_at_risk_minor=amount_at_risk_minor,
            )
        )
        revloop_results[-1]["amount_at_risk_minor"] = amount_at_risk_minor

        naive_results.append(
            evaluate_selected_action(
                selected=naive_selected,
                case_rows=all_case_rows,
                amount_at_risk_minor=amount_at_risk_minor,
            )
        )
        naive_results[-1]["amount_at_risk_minor"] = amount_at_risk_minor

    def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
        case_count = len(results)
        amount_at_risk = sum(entry["amount_at_risk_minor"] for entry in results)
        expected = sum(entry["expected_synthetic_recovered_minor"] for entry in results)
        realized = sum(entry["realized_synthetic_recovered_minor"] for entry in results)
        positive = sum(entry["recovered_within_72h"] for entry in results)
        return {
            "number_of_cases": case_count,
            "amount_at_risk_minor": amount_at_risk,
            "expected_synthetic_recovered_minor": expected,
            "realized_synthetic_recovered_minor": realized,
            "realized_recovery_rate": positive / case_count if case_count else 0.0,
            "selected_intervention_count": sum(1 for entry in results if entry["is_intervention"]),
            "contact_action_count": sum(1 for entry in results if entry["is_contact"]),
            "stop_count": sum(1 for entry in results if entry["is_stop"]),
            "no_selection_count": sum(1 for entry in results if entry["action_type"] is None),
        }

    revloop_summary = aggregate(revloop_results)
    naive_summary = aggregate(naive_results)
    return {
        "evaluation_label": "SYNTHETIC POLICY SIMULATION",
        "offline_evaluation_policy": "SYNTHETIC OFFLINE EVALUATION POLICY",
        "revloop_model_policy": revloop_summary,
        "naive_baseline_policy": naive_summary,
        "incremental_expected_recovered_minor": (
            revloop_summary["expected_synthetic_recovered_minor"]
            - naive_summary["expected_synthetic_recovered_minor"]
        ),
        "incremental_realized_recovered_minor": (
            revloop_summary["realized_synthetic_recovered_minor"]
            - naive_summary["realized_synthetic_recovered_minor"]
        ),
        "note": "One-step offline synthetic simulation; not multi-step workflow simulation.",
    }


def main(argv: list[str] | None = None) -> int:
    _configure_import_paths()
    from ml.common import CALIBRATION_BIN_COUNT, sha256_file
    from ml.train_baseline import (
        evaluate_split,
        load_training_frame,
        predictive_frame,
        split_frame,
        validate_split_integrity,
    )

    from app.ml.schemas import ModelBundleMetadata

    parser = argparse.ArgumentParser(description="Evaluate recovery baseline on test split.")
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--metrics", type=Path, required=True)
    args = parser.parse_args(argv)

    frame, summary = load_training_frame(csv_path=args.data, summary_path=args.summary)
    validate_split_integrity(frame)

    bundle = load_trusted_bundle(args.artifact)
    pipeline = bundle["model"]
    metadata = dict(bundle["metadata"])

    sidecar = json.loads(args.metadata.read_text(encoding="utf-8"))
    ModelBundleMetadata.model_validate(sidecar)

    artifact_sha256 = sha256_file(args.artifact)
    if sidecar.get("artifact_sha256") and sidecar["artifact_sha256"] != artifact_sha256:
        raise ValueError("Artifact SHA-256 does not match metadata sidecar.")

    validation_metrics = evaluate_split(
        pipeline=pipeline,
        frame=split_frame(frame, split_name="validation"),
        bin_count=CALIBRATION_BIN_COUNT,
    )
    test_metrics = evaluate_split(
        pipeline=pipeline,
        frame=split_frame(frame, split_name="test"),
        bin_count=CALIBRATION_BIN_COUNT,
    )
    policy_simulation = simulate_policy_on_test_cases(frame=frame, pipeline=pipeline)

    metrics_payload = {
        "evaluation_label": "SYNTHETIC MODEL EVALUATION",
        "model_version": metadata.get("model_version"),
        "model_family": metadata.get("model_family"),
        "feature_schema_version": summary["feature_schema_version"],
        "dataset": {
            "dataset_version": summary["dataset_version"],
            "seed": summary["seed"],
            "split_seed": summary["split_seed"],
            "training_data_sha256": sha256_file(args.data),
            "summary_sha256": sha256_file(args.summary),
            "artifact_sha256": artifact_sha256,
            "train_predictive_rows": len(predictive_frame(split_frame(frame, split_name="train"))),
            "validation_predictive_rows": validation_metrics["row_count"],
            "test_predictive_rows": test_metrics["row_count"],
        },
        "validation": validation_metrics,
        "test": test_metrics,
        "synthetic_policy_simulation": policy_simulation,
        "training_metadata": metadata,
    }

    args.metrics.parent.mkdir(parents=True, exist_ok=True)
    args.metrics.write_text(
        json.dumps(metrics_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"Wrote metrics {args.metrics}")
    print(f"test_roc_auc={test_metrics['roc_auc']:.4f}")
    print(
        "incremental_expected_recovered_minor="
        f"{policy_simulation['incremental_expected_recovered_minor']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
