#!/usr/bin/env python3
"""Train Logistic Regression recovery propensity baseline (Prompt 11)."""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


def _configure_import_paths() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    for path in (repo_root / "apps" / "api", repo_root / "scripts"):
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)


def _library_versions() -> dict[str, str]:
    import sklearn

    versions = {
        "scikit-learn": sklearn.__version__,
        "pandas": pd.__version__,
        "joblib": joblib.__version__,
        "numpy": np.__version__,
    }
    return versions


def build_preprocessing_pipeline(
    *,
    numeric_columns: tuple[str, ...],
    boolean_columns: tuple[str, ...],
    categorical_columns: tuple[str, ...],
) -> ColumnTransformer:
    return ColumnTransformer(
        transformers=[
            (
                "numeric",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="median")),
                        ("scaler", StandardScaler()),
                    ]
                ),
                list(numeric_columns),
            ),
            (
                "boolean",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                    ]
                ),
                list(boolean_columns),
            ),
            (
                "categorical",
                Pipeline(
                    [
                        (
                            "imputer",
                            SimpleImputer(strategy="constant", fill_value="UNKNOWN"),
                        ),
                        (
                            "onehot",
                            OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                        ),
                    ]
                ),
                list(categorical_columns),
            ),
        ],
        remainder="drop",
    )


def build_training_pipeline(*, seed: int) -> Pipeline:
    from ml.common import (
        BOOLEAN_FEATURE_COLUMNS,
        CATEGORICAL_FEATURE_COLUMNS,
        LOGISTIC_REGRESSION_CONFIG,
        NUMERICAL_FEATURE_COLUMNS,
    )

    classifier = LogisticRegression(
        random_state=seed,
        **LOGISTIC_REGRESSION_CONFIG,
    )
    return Pipeline(
        [
            (
                "preprocessor",
                build_preprocessing_pipeline(
                    numeric_columns=NUMERICAL_FEATURE_COLUMNS,
                    boolean_columns=BOOLEAN_FEATURE_COLUMNS,
                    categorical_columns=CATEGORICAL_FEATURE_COLUMNS,
                ),
            ),
            ("classifier", classifier),
        ]
    )


def load_training_frame(
    *, csv_path: Path, summary_path: Path
) -> tuple[pd.DataFrame, dict[str, Any]]:
    from ml.common import (
        BOOLEAN_FEATURE_COLUMNS,
        FEATURE_COLUMNS,
        NUMERICAL_FEATURE_COLUMNS,
        assert_feature_allowlist,
        load_dataset_summary,
        parse_boolean_token,
        read_raw_csv_header,
        validate_raw_csv_header,
    )

    summary = load_dataset_summary(summary_path)
    header = read_raw_csv_header(csv_path)
    validate_raw_csv_header(header)
    assert_feature_allowlist(FEATURE_COLUMNS)

    frame = pd.read_csv(csv_path)
    if list(frame.columns) != list(header):
        raise ValueError("pandas column order does not match raw CSV header.")

    for column in NUMERICAL_FEATURE_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in BOOLEAN_FEATURE_COLUMNS:
        frame[column] = frame[column].map(parse_boolean_token).astype(int)
    for column in FEATURE_COLUMNS:
        if column not in BOOLEAN_FEATURE_COLUMNS and column not in NUMERICAL_FEATURE_COLUMNS:
            frame[column] = frame[column].astype(str)

    return frame, summary


def validate_split_integrity(frame: pd.DataFrame) -> None:
    from ml.common import load_dataset_summary

    _ = load_dataset_summary  # import side-effect unused; kept for symmetry
    group_column = "case_id"
    split_column = "split"
    case_splits = frame.groupby(group_column)[split_column].nunique()
    if (case_splits > 1).any():
        raise ValueError("case_id appears in more than one split.")

    train_cases = set(frame.loc[frame["split"] == "train", group_column])
    valid_cases = set(frame.loc[frame["split"] == "validation", group_column])
    test_cases = set(frame.loc[frame["split"] == "test", group_column])
    if train_cases.intersection(valid_cases):
        raise ValueError("train/validation case overlap detected.")
    if train_cases.intersection(test_cases):
        raise ValueError("train/test case overlap detected.")
    if valid_cases.intersection(test_cases):
        raise ValueError("validation/test case overlap detected.")


def predictive_frame(frame: pd.DataFrame) -> pd.DataFrame:
    from ml.common import is_stop_action

    return frame.loc[~frame["action_type"].map(is_stop_action)].copy()


def split_frame(frame: pd.DataFrame, *, split_name: str) -> pd.DataFrame:
    return frame.loc[frame["split"] == split_name].copy()


def build_calibration_bins(
    *,
    probabilities: np.ndarray,
    labels: np.ndarray,
    bin_count: int,
) -> list[dict[str, Any]]:
    bins: list[dict[str, Any]] = []
    edges = np.linspace(0.0, 1.0, bin_count + 1)
    for index in range(bin_count):
        lower = float(edges[index])
        upper = float(edges[index + 1])
        if index < bin_count - 1:
            mask = (probabilities >= lower) & (probabilities < upper)
        else:
            mask = (probabilities >= lower) & (probabilities <= upper)
        count = int(mask.sum())
        if count == 0:
            bins.append(
                {
                    "lower_bound": lower,
                    "upper_bound": upper,
                    "count": 0,
                    "mean_predicted_probability": None,
                    "empirical_recovery_rate": None,
                }
            )
            continue
        mean_pred = float(probabilities[mask].mean())
        empirical = float(labels[mask].mean())
        bins.append(
            {
                "lower_bound": lower,
                "count": count,
                "upper_bound": upper,
                "mean_predicted_probability": mean_pred,
                "empirical_recovery_rate": empirical,
            }
        )
    return bins


def compute_expected_calibration_error(bins: list[dict[str, Any]]) -> float:
    total = sum(bin_entry["count"] for bin_entry in bins)
    if total == 0:
        return 0.0
    error = 0.0
    for bin_entry in bins:
        if bin_entry["count"] == 0:
            continue
        weight = bin_entry["count"] / total
        predicted = bin_entry["mean_predicted_probability"]
        empirical = bin_entry["empirical_recovery_rate"]
        error += weight * abs(predicted - empirical)
    return float(error)


def compute_probability_metrics(
    *,
    labels: np.ndarray,
    probabilities: np.ndarray,
    bin_count: int,
) -> dict[str, Any]:
    if labels.size == 0:
        raise ValueError("Cannot compute metrics on empty label set.")
    if not np.isfinite(probabilities).all():
        raise ValueError("Predicted probabilities must be finite.")
    if ((probabilities < 0) | (probabilities > 1)).any():
        raise ValueError("Predicted probabilities must lie within [0, 1].")
    if len(np.unique(labels)) < 2:
        raise ValueError("Both target classes are required for binary probability metrics.")

    calibration_bins = build_calibration_bins(
        probabilities=probabilities,
        labels=labels,
        bin_count=bin_count,
    )
    return {
        "row_count": int(labels.size),
        "case_count": None,
        "positive_count": int(labels.sum()),
        "negative_count": int(labels.size - labels.sum()),
        "positive_rate": float(labels.mean()),
        "roc_auc": float(roc_auc_score(labels, probabilities)),
        "pr_auc": float(average_precision_score(labels, probabilities)),
        "log_loss": float(log_loss(labels, probabilities)),
        "brier_score": float(brier_score_loss(labels, probabilities)),
        "calibration_bins": calibration_bins,
        "expected_calibration_error": compute_expected_calibration_error(calibration_bins),
    }


def per_action_diagnostics(
    *,
    frame: pd.DataFrame,
    probabilities: np.ndarray,
) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {}
    labels = frame["recovered_within_72h"].astype(int).to_numpy()
    for action_type, group in frame.groupby("action_type"):
        indices = group.index.to_numpy()
        position_map = {index: position for position, index in enumerate(frame.index.to_list())}
        positions = [position_map[index] for index in indices]
        action_probs = probabilities[positions]
        action_labels = labels[positions]
        entry: dict[str, Any] = {
            "row_count": len(group),
            "positive_rate": float(action_labels.mean()) if len(action_labels) else 0.0,
            "mean_predicted_probability": float(action_probs.mean()) if len(action_probs) else 0.0,
            "mean_observed_label": float(action_labels.mean()) if len(action_labels) else 0.0,
        }
        if len(np.unique(action_labels)) < 2:
            entry["roc_auc"] = None
            entry["reason"] = "single_class"
        else:
            entry["roc_auc"] = float(roc_auc_score(action_labels, action_probs))
        diagnostics[str(action_type)] = entry
    return diagnostics


def fit_baseline_model(*, frame: pd.DataFrame, seed: int) -> Pipeline:
    from ml.common import FEATURE_COLUMNS

    train_predictive = predictive_frame(split_frame(frame, split_name="train"))
    pipeline = build_training_pipeline(seed=seed)
    x_train = train_predictive[list(FEATURE_COLUMNS)]
    y_train = train_predictive["recovered_within_72h"].astype(int).to_numpy()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ConvergenceWarning)
        pipeline.fit(x_train, y_train)

    convergence_warnings = [
        message for message in caught if issubclass(message.category, ConvergenceWarning)
    ]
    if convergence_warnings:
        raise RuntimeError("LogisticRegression failed to converge.")

    classifier = pipeline.named_steps["classifier"]
    if hasattr(classifier, "n_iter_") and classifier.n_iter_ >= classifier.max_iter:
        raise RuntimeError("LogisticRegression reached max_iter without convergence.")

    return pipeline


def predict_positive_probabilities(
    pipeline: Pipeline,
    frame: pd.DataFrame,
) -> np.ndarray:
    from ml.common import FEATURE_COLUMNS

    probabilities = pipeline.predict_proba(frame[list(FEATURE_COLUMNS)])
    return probabilities[:, 1]


def evaluate_split(
    *,
    pipeline: Pipeline,
    frame: pd.DataFrame,
    bin_count: int,
) -> dict[str, Any]:
    predictive = predictive_frame(frame)
    probabilities = predict_positive_probabilities(pipeline, predictive)
    labels = predictive["recovered_within_72h"].astype(int).to_numpy()
    metrics = compute_probability_metrics(
        labels=labels,
        probabilities=probabilities,
        bin_count=bin_count,
    )
    metrics["case_count"] = int(predictive["case_id"].nunique())
    metrics["per_action"] = per_action_diagnostics(
        frame=predictive,
        probabilities=probabilities,
    )
    return metrics


def build_metadata(
    *,
    summary: dict[str, Any],
    frame: pd.DataFrame,
    validation_metrics: dict[str, Any],
    training_data_sha256: str,
    summary_sha256: str,
    seed: int,
    trained_at: str,
) -> dict[str, Any]:
    from ml.common import (
        ARTIFACT_FORMAT_VERSION,
        BOOLEAN_FEATURE_COLUMNS,
        CATEGORICAL_FEATURE_COLUMNS,
        FEATURE_COLUMNS,
        LOGISTIC_REGRESSION_CONFIG,
        MODEL_FAMILY,
        MODEL_VERSION,
        NUMERICAL_FEATURE_COLUMNS,
        PREDICTIVE_ACTION_TYPES,
    )

    train_rows = predictive_frame(split_frame(frame, split_name="train"))
    valid_rows = predictive_frame(split_frame(frame, split_name="validation"))
    return {
        "artifact_format_version": ARTIFACT_FORMAT_VERSION,
        "model_version": MODEL_VERSION,
        "model_family": MODEL_FAMILY,
        "feature_schema_version": summary["feature_schema_version"],
        "dataset_version": summary["dataset_version"],
        "training_seed": seed,
        "split_seed": summary["split_seed"],
        "training_case_count": int(train_rows["case_id"].nunique()),
        "training_row_count": len(train_rows),
        "validation_case_count": int(valid_rows["case_id"].nunique()),
        "validation_row_count": len(valid_rows),
        "feature_columns": list(FEATURE_COLUMNS),
        "numeric_feature_columns": list(NUMERICAL_FEATURE_COLUMNS),
        "boolean_feature_columns": list(BOOLEAN_FEATURE_COLUMNS),
        "categorical_feature_columns": list(CATEGORICAL_FEATURE_COLUMNS),
        "action_types": list(PREDICTIVE_ACTION_TYPES),
        "deterministic_action_probabilities": {"STOP": 0.0},
        "training_configuration": {
            "estimator": "LogisticRegression",
            **LOGISTIC_REGRESSION_CONFIG,
            "random_state": seed,
            "numeric_preprocessing": ["SimpleImputer(median)", "StandardScaler"],
            "boolean_preprocessing": ["SimpleImputer(most_frequent)"],
            "categorical_preprocessing": [
                "SimpleImputer(constant=UNKNOWN)",
                "OneHotEncoder(handle_unknown=ignore)",
            ],
            "stop_excluded_from_training": True,
        },
        "library_versions": _library_versions(),
        "validation_metrics": validation_metrics,
        "training_data_sha256": training_data_sha256,
        "summary_sha256": summary_sha256,
        "trained_at": trained_at,
    }


def main(argv: list[str] | None = None) -> int:
    _configure_import_paths()
    from ml.common import CALIBRATION_BIN_COUNT, sha256_file

    parser = argparse.ArgumentParser(description="Train Logistic Regression recovery baseline.")
    parser.add_argument("--data", type=Path, required=True, help="training_data.csv path")
    parser.add_argument("--summary", type=Path, required=True, help="summary.json path")
    parser.add_argument("--artifact", type=Path, required=True, help="Output joblib artifact path")
    parser.add_argument(
        "--metadata",
        type=Path,
        required=True,
        help="Output metadata sidecar JSON path",
    )
    parser.add_argument("--seed", type=int, default=20260901, help="Training random seed")
    args = parser.parse_args(argv)

    frame, summary = load_training_frame(csv_path=args.data, summary_path=args.summary)
    validate_split_integrity(frame)

    pipeline = fit_baseline_model(frame=frame, seed=args.seed)
    validation_metrics = evaluate_split(
        pipeline=pipeline,
        frame=split_frame(frame, split_name="validation"),
        bin_count=CALIBRATION_BIN_COUNT,
    )

    trained_at = datetime.now(tz=timezone.utc).isoformat()
    training_data_sha256 = sha256_file(args.data)
    summary_sha256 = sha256_file(args.summary)
    metadata = build_metadata(
        summary=summary,
        frame=frame,
        validation_metrics=validation_metrics,
        training_data_sha256=training_data_sha256,
        summary_sha256=summary_sha256,
        seed=args.seed,
        trained_at=trained_at,
    )

    args.artifact.parent.mkdir(parents=True, exist_ok=True)
    bundle = {"model": pipeline, "metadata": metadata}
    joblib.dump(bundle, args.artifact)

    artifact_sha256 = sha256_file(args.artifact)
    metadata["artifact_sha256"] = artifact_sha256
    metadata["artifact_file"] = str(args.artifact)

    args.metadata.parent.mkdir(parents=True, exist_ok=True)
    args.metadata.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(f"Wrote artifact {args.artifact}")
    print(f"Wrote metadata {args.metadata}")
    print(f"validation_roc_auc={validation_metrics['roc_auc']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
