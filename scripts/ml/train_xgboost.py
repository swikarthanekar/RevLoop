#!/usr/bin/env python3
"""Train restrained XGBoost recovery propensity challenger (Prompt 12)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBClassifier


def _configure_import_paths() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    for path in (repo_root / "apps" / "api", repo_root / "scripts"):
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)


def _library_versions() -> dict[str, Any]:
    import joblib as joblib_module
    import sklearn
    import xgboost

    return {
        "scikit-learn": sklearn.__version__,
        "pandas": pd.__version__,
        "joblib": joblib_module.__version__,
        "numpy": np.__version__,
        "xgboost": xgboost.__version__,
    }


def build_xgboost_preprocessing_pipeline(
    *,
    numeric_columns: tuple[str, ...],
    boolean_columns: tuple[str, ...],
    categorical_columns: tuple[str, ...],
) -> ColumnTransformer:
    """XGBoost preprocessing: same imputation semantics as LR, no numeric scaling."""
    return ColumnTransformer(
        transformers=[
            (
                "numeric",
                Pipeline([("imputer", SimpleImputer(strategy="median"))]),
                list(numeric_columns),
            ),
            (
                "boolean",
                Pipeline([("imputer", SimpleImputer(strategy="most_frequent"))]),
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


def build_xgb_classifier(*, seed: int) -> XGBClassifier:
    from ml.common import XGBOOST_CONFIG, XGBOOST_EARLY_STOPPING_ROUNDS

    params = dict(XGBOOST_CONFIG)
    params["random_state"] = seed
    params["early_stopping_rounds"] = XGBOOST_EARLY_STOPPING_ROUNDS
    return XGBClassifier(**params)


def fit_xgboost_candidate(*, frame: pd.DataFrame, seed: int) -> tuple[Pipeline, dict[str, Any]]:
    from ml.common import (
        BOOLEAN_FEATURE_COLUMNS,
        CALIBRATION_BIN_COUNT,
        CATEGORICAL_FEATURE_COLUMNS,
        FEATURE_COLUMNS,
        NUMERICAL_FEATURE_COLUMNS,
        XGBOOST_CONFIG,
        decide_calibration_method,
    )
    from ml.train_baseline import (
        evaluate_split,
        predictive_frame,
        split_frame,
    )

    train_predictive = predictive_frame(split_frame(frame, split_name="train"))
    valid_predictive = predictive_frame(split_frame(frame, split_name="validation"))

    preprocessor = build_xgboost_preprocessing_pipeline(
        numeric_columns=NUMERICAL_FEATURE_COLUMNS,
        boolean_columns=BOOLEAN_FEATURE_COLUMNS,
        categorical_columns=CATEGORICAL_FEATURE_COLUMNS,
    )
    x_train = train_predictive[list(FEATURE_COLUMNS)]
    y_train = train_predictive["recovered_within_72h"].astype(int).to_numpy()
    x_valid = valid_predictive[list(FEATURE_COLUMNS)]
    y_valid = valid_predictive["recovered_within_72h"].astype(int).to_numpy()

    preprocessor.fit(x_train)
    x_train_transformed = preprocessor.transform(x_train)
    x_valid_transformed = preprocessor.transform(x_valid)

    classifier = build_xgb_classifier(seed=seed)
    classifier.fit(
        x_train_transformed,
        y_train,
        eval_set=[(x_valid_transformed, y_valid)],
        verbose=False,
    )

    uncalibrated_pipeline = Pipeline(
        [
            ("preprocessor", preprocessor),
            ("classifier", classifier),
        ]
    )
    uncalibrated_validation_metrics = evaluate_split(
        pipeline=uncalibrated_pipeline,
        frame=split_frame(frame, split_name="validation"),
        bin_count=CALIBRATION_BIN_COUNT,
    )
    calibration = decide_calibration_method(
        uncalibrated_validation_metrics=uncalibrated_validation_metrics,
    )

    final_classifier: Any = classifier
    validation_calibration_fit_metrics: dict[str, Any] | None = None
    if calibration.method == "sigmoid":
        calibrated = CalibratedClassifierCV(
            estimator=classifier,
            method="sigmoid",
            cv="prefit",
        )
        calibrated.fit(x_valid_transformed, y_valid)
        final_classifier = calibrated
        validation_calibration_fit_metrics = evaluate_split(
            pipeline=Pipeline([("preprocessor", preprocessor), ("classifier", calibrated)]),
            frame=split_frame(frame, split_name="validation"),
            bin_count=CALIBRATION_BIN_COUNT,
        )

    pipeline = Pipeline(
        [
            ("preprocessor", preprocessor),
            ("classifier", final_classifier),
        ]
    )

    training_details = {
        "configured_n_estimators": int(XGBOOST_CONFIG["n_estimators"]),
        "best_iteration": int(classifier.best_iteration),
        "best_score": float(classifier.best_score),
        "early_stopping_metric": "logloss",
        "early_stopping_rounds": int(classifier.early_stopping_rounds),
        "calibration_method": calibration.method,
        "calibration_reason": calibration.reason,
        "uncalibrated_validation_brier": calibration.uncalibrated_validation_brier,
        "uncalibrated_validation_log_loss": calibration.uncalibrated_validation_log_loss,
        "uncalibrated_validation_ece": calibration.uncalibrated_validation_ece,
        "validation_calibration_fit_metrics": validation_calibration_fit_metrics,
        "uncalibrated_validation_metrics": uncalibrated_validation_metrics,
    }
    return pipeline, training_details


def build_metadata(
    *,
    summary: dict[str, Any],
    frame: pd.DataFrame,
    validation_metrics: dict[str, Any],
    training_details: dict[str, Any],
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
        NUMERICAL_FEATURE_COLUMNS,
        PREDICTIVE_ACTION_TYPES,
        XGBOOST_CONFIG,
        XGBOOST_MODEL_FAMILY,
        XGBOOST_MODEL_VERSION,
    )
    from ml.train_baseline import predictive_frame, split_frame

    train_rows = predictive_frame(split_frame(frame, split_name="train"))
    valid_rows = predictive_frame(split_frame(frame, split_name="validation"))
    return {
        "artifact_format_version": ARTIFACT_FORMAT_VERSION,
        "model_version": XGBOOST_MODEL_VERSION,
        "model_family": XGBOOST_MODEL_FAMILY,
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
            "estimator": "XGBClassifier",
            **XGBOOST_CONFIG,
            "early_stopping_rounds": training_details["early_stopping_rounds"],
            "random_state": seed,
            "numeric_preprocessing": ["SimpleImputer(median)"],
            "boolean_preprocessing": ["SimpleImputer(most_frequent)"],
            "categorical_preprocessing": [
                "SimpleImputer(constant=UNKNOWN)",
                "OneHotEncoder(handle_unknown=ignore)",
            ],
            "stop_excluded_from_training": True,
            "calibration_method": training_details["calibration_method"],
            "calibration_reason": training_details["calibration_reason"],
        },
        "training_details": training_details,
        "library_versions": _library_versions(),
        "validation_metrics": validation_metrics,
        "training_data_sha256": training_data_sha256,
        "summary_sha256": summary_sha256,
        "trained_at": trained_at,
        "candidate_status": "pending_selection",
    }


def main(argv: list[str] | None = None) -> int:
    _configure_import_paths()
    from ml.common import CALIBRATION_BIN_COUNT, sha256_file
    from ml.train_baseline import (
        evaluate_split,
        load_training_frame,
        split_frame,
        validate_split_integrity,
    )

    parser = argparse.ArgumentParser(description="Train XGBoost recovery challenger.")
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260901)
    args = parser.parse_args(argv)

    frame, summary = load_training_frame(csv_path=args.data, summary_path=args.summary)
    validate_split_integrity(frame)

    pipeline, training_details = fit_xgboost_candidate(frame=frame, seed=args.seed)
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
        training_details=training_details,
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
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"Wrote artifact {args.artifact}")
    print(f"Wrote metadata {args.metadata}")
    print(f"best_iteration={training_details['best_iteration']}")
    print(f"calibration_method={training_details['calibration_method']}")
    print(f"validation_roc_auc={validation_metrics['roc_auc']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
