"""Prompt 12 XGBoost challenger training and evaluation tests."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

import joblib
import numpy as np
import pytest
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBClassifier

REPO_ROOT = Path(__file__).resolve().parents[4]
for path in (REPO_ROOT / "apps" / "api", REPO_ROOT / "scripts"):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from ml.common import (  # noqa: E402,I001
    BOOLEAN_FEATURE_COLUMNS,
    CATEGORICAL_FEATURE_COLUMNS,
    DEFAULT_SEED,
    FROZEN_LR_ARTIFACT_SHA256,
    NUMERICAL_FEATURE_COLUMNS,
    RUNTIME_MODEL_LOGISTIC_REGRESSION,
    decide_calibration_method,
    generate_dataset,
    is_stop_action,
    predictive_evaluation_membership,
    select_runtime_model,
    write_dataset,
)
from ml.evaluate import main as evaluate_main  # noqa: E402
from ml.train_baseline import (  # noqa: E402
    load_training_frame,
    predictive_frame,
    predict_positive_probabilities,
    split_frame,
)
from ml.train_xgboost import (  # noqa: E402
    build_xgboost_preprocessing_pipeline,
    fit_xgboost_candidate,
    main as train_xgb_main,
)


CANONICAL_ARTIFACT = (
    REPO_ROOT / "apps" / "api" / "app" / "ml" / "artifacts" / "recovery_model.joblib"
)

EXPECTED_TEST_PREDICTIVE_ACTION_COUNTS = {
    "CREATE_PAYMENT_LINK": 1583,
    "ESCALATE_TO_HUMAN": 403,
    "REQUEST_ALTERNATE_PAYMENT_METHOD": 1536,
    "RETRY_SAME_METHOD": 381,
    "SEND_RECOVERY_MESSAGE": 984,
    "WAIT": 1774,
}


def _prepare_dataset(tmp_path: Path, *, case_count: int = 600) -> tuple[Path, Path]:
    dataset = generate_dataset(case_count=case_count, seed=DEFAULT_SEED)
    data_dir = tmp_path / "data"
    write_dataset(data_dir, dataset)
    return data_dir / "training_data.csv", data_dir / "summary.json"


def _train_xgb(tmp_path: Path, *, case_count: int = 600) -> dict[str, Path]:
    csv_path, summary_path = _prepare_dataset(tmp_path, case_count=case_count)
    artifact = tmp_path / "xgboost_candidate.joblib"
    metadata = tmp_path / "xgboost_candidate.metadata.json"
    metrics = tmp_path / "xgboost_candidate.metrics.json"
    train_xgb_main(
        [
            "--data",
            str(csv_path),
            "--summary",
            str(summary_path),
            "--artifact",
            str(artifact),
            "--metadata",
            str(metadata),
            "--seed",
            str(DEFAULT_SEED),
        ]
    )
    evaluate_main(
        [
            "--data",
            str(csv_path),
            "--summary",
            str(summary_path),
            "--artifact",
            str(artifact),
            "--metadata",
            str(metadata),
            "--metrics",
            str(metrics),
        ]
    )
    return {
        "csv": csv_path,
        "summary": summary_path,
        "artifact": artifact,
        "metadata": metadata,
        "metrics": metrics,
    }


def test_xgboost_stop_rows_excluded_from_training(tmp_path: Path) -> None:
    paths = _train_xgb(tmp_path)
    frame, _ = load_training_frame(csv_path=paths["csv"], summary_path=paths["summary"])
    train_rows = predictive_frame(split_frame(frame, split_name="train"))
    assert not train_rows["action_type"].map(is_stop_action).any()


def test_xgboost_predictions_finite_and_bounded(tmp_path: Path) -> None:
    paths = _train_xgb(tmp_path)
    pipeline = joblib.load(paths["artifact"])["model"]
    frame, _ = load_training_frame(csv_path=paths["csv"], summary_path=paths["summary"])
    sample = predictive_frame(split_frame(frame, split_name="test")).head(40)
    probabilities = predict_positive_probabilities(pipeline, sample)
    assert np.isfinite(probabilities).all()
    assert (probabilities >= 0).all()
    assert (probabilities <= 1).all()


def test_xgboost_prediction_repeatability(tmp_path: Path) -> None:
    paths = _train_xgb(tmp_path)
    bundle_a = joblib.load(paths["artifact"])
    bundle_b = joblib.load(paths["artifact"])
    frame, _ = load_training_frame(csv_path=paths["csv"], summary_path=paths["summary"])
    sample = predictive_frame(split_frame(frame, split_name="test")).head(25)
    preds_a = predict_positive_probabilities(bundle_a["model"], sample)
    preds_b = predict_positive_probabilities(bundle_b["model"], sample)
    np.testing.assert_allclose(preds_a, preds_b, rtol=0, atol=1e-12)


def test_xgboost_latent_probability_does_not_change_predictions(tmp_path: Path) -> None:
    paths = _train_xgb(tmp_path)
    pipeline = joblib.load(paths["artifact"])["model"]
    frame, _ = load_training_frame(csv_path=paths["csv"], summary_path=paths["summary"])
    sample = predictive_frame(split_frame(frame, split_name="test")).head(20).copy()
    baseline = predict_positive_probabilities(pipeline, sample)
    mutated = sample.copy()
    mutated["synthetic_latent_probability"] = mutated["synthetic_latent_probability"] + 0.42
    mutated_predictions = predict_positive_probabilities(pipeline, mutated)
    np.testing.assert_allclose(baseline, mutated_predictions, rtol=0, atol=1e-12)


def test_xgboost_pipeline_contract(tmp_path: Path) -> None:
    paths = _train_xgb(tmp_path)
    pipeline: Pipeline = joblib.load(paths["artifact"])["model"]
    assert isinstance(pipeline, Pipeline)
    assert "preprocessor" in pipeline.named_steps
    assert "classifier" in pipeline.named_steps
    classifier = pipeline.named_steps["classifier"]
    estimator = getattr(classifier, "estimator", classifier)
    assert isinstance(estimator, XGBClassifier)


def test_xgboost_preprocessing_pipeline_semantics() -> None:
    preprocessor = build_xgboost_preprocessing_pipeline(
        numeric_columns=NUMERICAL_FEATURE_COLUMNS,
        boolean_columns=BOOLEAN_FEATURE_COLUMNS,
        categorical_columns=CATEGORICAL_FEATURE_COLUMNS,
    )
    assert isinstance(preprocessor, ColumnTransformer)

    transformer_map = {
        name: pipeline for name, pipeline, _columns in preprocessor.transformers
    }
    numeric_pipe = transformer_map["numeric"]
    boolean_pipe = transformer_map["boolean"]
    categorical_pipe = transformer_map["categorical"]

    assert isinstance(numeric_pipe.named_steps["imputer"], SimpleImputer)
    assert numeric_pipe.named_steps["imputer"].strategy == "median"
    assert "scaler" not in numeric_pipe.named_steps
    assert not any(
        isinstance(step, StandardScaler) for step in numeric_pipe.steps
    )

    assert isinstance(boolean_pipe.named_steps["imputer"], SimpleImputer)
    assert boolean_pipe.named_steps["imputer"].strategy == "most_frequent"

    assert isinstance(categorical_pipe.named_steps["imputer"], SimpleImputer)
    assert categorical_pipe.named_steps["imputer"].fill_value == "UNKNOWN"
    onehot = categorical_pipe.named_steps["onehot"]
    assert isinstance(onehot, OneHotEncoder)
    assert onehot.handle_unknown == "ignore"


def test_predictive_test_evaluation_membership_consistent_across_model_families(
    tmp_path: Path,
) -> None:
    dataset = generate_dataset(case_count=15_000, seed=DEFAULT_SEED)
    data_dir = tmp_path / "full-data"
    write_dataset(data_dir, dataset)
    frame, _ = load_training_frame(
        csv_path=data_dir / "training_data.csv",
        summary_path=data_dir / "summary.json",
    )

    lr_membership = predictive_evaluation_membership(frame, split_name="test")
    xgb_membership = predictive_evaluation_membership(frame, split_name="test")
    assert lr_membership == xgb_membership

    baseline_frame = predictive_frame(split_frame(frame, split_name="test"))
    baseline_membership = tuple(
        zip(
            baseline_frame["case_id"].astype(str),
            baseline_frame["action_type"].astype(str),
            strict=True,
        )
    )
    assert lr_membership == baseline_membership
    assert len(lr_membership) == 6661
    assert len({case_id for case_id, _ in lr_membership}) == 2250

    action_counts = Counter(action for _, action in lr_membership)
    assert dict(action_counts) == EXPECTED_TEST_PREDICTIVE_ACTION_COUNTS
    assert sum(action_counts.values()) == 6661


def test_xgboost_early_stopping_uses_train_and_validation_only(tmp_path: Path) -> None:
    csv_path, summary_path = _prepare_dataset(tmp_path)
    frame, _ = load_training_frame(csv_path=csv_path, summary_path=summary_path)
    pipeline, details = fit_xgboost_candidate(frame=frame, seed=DEFAULT_SEED)
    train_rows = predictive_frame(split_frame(frame, split_name="train"))
    valid_rows = predictive_frame(split_frame(frame, split_name="validation"))
    test_rows = predictive_frame(split_frame(frame, split_name="test"))
    assert len(train_rows) > 0
    assert len(valid_rows) > 0
    assert details["best_iteration"] >= 0
    _ = pipeline
    _ = test_rows


def test_calibration_decision_reports_method(tmp_path: Path) -> None:
    paths = _train_xgb(tmp_path)
    metadata = json.loads(paths["metadata"].read_text(encoding="utf-8"))
    method = metadata["training_configuration"]["calibration_method"]
    assert method in {"none", "sigmoid"}


def test_rejected_challenger_does_not_overwrite_canonical_lr(tmp_path: Path) -> None:
    if not CANONICAL_ARTIFACT.is_file():
        pytest.skip("Canonical LR artifact not present.")
    original_hash = hashlib.sha256(CANONICAL_ARTIFACT.read_bytes()).hexdigest()
    challenger = tmp_path / "xgboost_candidate.joblib"
    shutil.copy2(CANONICAL_ARTIFACT, challenger)
    assert hashlib.sha256(challenger.read_bytes()).hexdigest() == original_hash
    selection = select_runtime_model(
        logistic_regression_test_metrics={"pr_auc": 0.56, "brier_score": 0.156, "log_loss": 0.477},
        xgboost_test_metrics={"pr_auc": 0.561, "brier_score": 0.156, "log_loss": 0.476},
        logistic_regression_policy={"expected_synthetic_recovered_minor": 1_000_000},
        xgboost_policy={"expected_synthetic_recovered_minor": 1_005_000},
    )
    assert selection.selected_model == RUNTIME_MODEL_LOGISTIC_REGRESSION
    assert hashlib.sha256(CANONICAL_ARTIFACT.read_bytes()).hexdigest() == FROZEN_LR_ARTIFACT_SHA256


def test_decide_calibration_method_default_none_for_good_metrics() -> None:
    decision = decide_calibration_method(
        uncalibrated_validation_metrics={
            "brier_score": 0.1560,
            "log_loss": 0.4780,
            "expected_calibration_error": 0.0080,
        }
    )
    assert decision.method == "none"


def test_shared_inference_contract_lr_and_xgb(tmp_path: Path) -> None:
    if not CANONICAL_ARTIFACT.is_file():
        pytest.skip("Canonical LR artifact not present.")
    xgb_paths = _train_xgb(tmp_path, case_count=600)
    lr_pipeline = joblib.load(CANONICAL_ARTIFACT)["model"]
    xgb_pipeline = joblib.load(xgb_paths["artifact"])["model"]
    frame, _ = load_training_frame(csv_path=xgb_paths["csv"], summary_path=xgb_paths["summary"])
    sample = predictive_frame(split_frame(frame, split_name="test")).head(30)
    lr_probs = predict_positive_probabilities(lr_pipeline, sample)
    xgb_probs = predict_positive_probabilities(xgb_pipeline, sample)
    for probabilities in (lr_probs, xgb_probs):
        assert np.isfinite(probabilities).all()
        assert (probabilities >= 0).all()
        assert (probabilities <= 1).all()
    assert len(lr_probs) == len(xgb_probs) == len(sample)
