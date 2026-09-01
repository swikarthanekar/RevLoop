"""Prompt 11 Logistic Regression baseline training and evaluation tests."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pytest
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

REPO_ROOT = Path(__file__).resolve().parents[4]
for path in (REPO_ROOT / "apps" / "api", REPO_ROOT / "scripts"):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from app.ml.schemas import ModelBundleMetadata  # noqa: E402,I001
from app.recovery.schemas import FEATURE_SCHEMA_VERSION  # noqa: E402,I001
from ml.common import (  # noqa: E402,I001
    CSV_COLUMNS,
    DATASET_VERSION,
    DEFAULT_SEED,
    FEATURE_COLUMNS,
    FORBIDDEN_FEATURE_COLUMNS,
    MODEL_VERSION,
    decode_amount_at_risk_minor,
    generate_dataset,
    is_stop_action,
    write_dataset,
)
from ml.evaluate import main as evaluate_main  # noqa: E402
from ml.train_baseline import (  # noqa: E402
    fit_baseline_model,
    load_training_frame,
    main as train_main,
    predictive_frame,
    split_frame,
)


def _prepare_dataset(tmp_path: Path, *, case_count: int = 600) -> tuple[Path, Path]:
    dataset = generate_dataset(case_count=case_count, seed=DEFAULT_SEED)
    data_dir = tmp_path / "data"
    write_dataset(data_dir, dataset)
    return data_dir / "training_data.csv", data_dir / "summary.json"


def _train_and_evaluate(
    tmp_path: Path,
    *,
    case_count: int = 600,
) -> dict[str, Path]:
    csv_path, summary_path = _prepare_dataset(tmp_path, case_count=case_count)
    artifact = tmp_path / "recovery_model.joblib"
    metadata = tmp_path / "recovery_model.metadata.json"
    metrics = tmp_path / "recovery_model.metrics.json"
    train_main(
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


def test_decode_amount_at_risk_minor_roundtrip() -> None:
    for amount in (0, 149_900, 5_000, 2_500_000):
        decoded = decode_amount_at_risk_minor(np.log1p(amount))
        assert decoded == amount


def test_stop_rows_excluded_from_training_and_metrics(tmp_path: Path) -> None:
    paths = _train_and_evaluate(tmp_path)
    frame, _ = load_training_frame(csv_path=paths["csv"], summary_path=paths["summary"])
    train_rows = predictive_frame(split_frame(frame, split_name="train"))
    assert not train_rows["action_type"].map(is_stop_action).any()

    metrics = json.loads(paths["metrics"].read_text(encoding="utf-8"))
    test_rows = split_frame(frame, split_name="test")
    predictive_test = predictive_frame(test_rows)
    assert metrics["test"]["row_count"] == len(predictive_test)
    assert metrics["test"]["calibration_bins"]
    bin_total = sum(bin_entry["count"] for bin_entry in metrics["test"]["calibration_bins"])
    assert bin_total == metrics["test"]["row_count"]


def test_model_features_exclude_leakage_columns(tmp_path: Path) -> None:
    paths = _train_and_evaluate(tmp_path)
    bundle = joblib.load(paths["artifact"])
    metadata = bundle["metadata"]
    assert FORBIDDEN_FEATURE_COLUMNS.isdisjoint(set(metadata["feature_columns"]))
    assert "synthetic_latent_probability" not in metadata["feature_columns"]
    assert "recovered_within_72h" not in metadata["feature_columns"]
    assert "case_id" not in metadata["feature_columns"]
    assert "split" not in metadata["feature_columns"]


def test_changing_latent_probability_does_not_change_predictions(tmp_path: Path) -> None:
    paths = _train_and_evaluate(tmp_path)
    bundle = joblib.load(paths["artifact"])
    pipeline = bundle["model"]
    frame, _ = load_training_frame(csv_path=paths["csv"], summary_path=paths["summary"])
    sample = predictive_frame(split_frame(frame, split_name="test")).head(20).copy()
    baseline = pipeline.predict_proba(sample[list(FEATURE_COLUMNS)])[:, 1]

    mutated = sample.copy()
    mutated["synthetic_latent_probability"] = mutated["synthetic_latent_probability"] + 0.5
    mutated_predictions = pipeline.predict_proba(mutated[list(FEATURE_COLUMNS)])[:, 1]
    np.testing.assert_allclose(baseline, mutated_predictions, rtol=0, atol=1e-12)


def test_pipeline_contract_contains_expected_steps(tmp_path: Path) -> None:
    paths = _train_and_evaluate(tmp_path)
    pipeline: Pipeline = joblib.load(paths["artifact"])["model"]
    assert isinstance(pipeline, Pipeline)
    preprocessor = pipeline.named_steps["preprocessor"]
    classifier = pipeline.named_steps["classifier"]
    assert isinstance(preprocessor, ColumnTransformer)
    assert isinstance(classifier, LogisticRegression)
    transformer_names = {name for name, _, _ in preprocessor.transformers}
    assert transformer_names == {"numeric", "boolean", "categorical"}


def test_artifact_load_and_metadata_validation(tmp_path: Path) -> None:
    paths = _train_and_evaluate(tmp_path)
    bundle = joblib.load(paths["artifact"])
    sidecar = json.loads(paths["metadata"].read_text(encoding="utf-8"))
    metadata = ModelBundleMetadata.model_validate(sidecar)
    assert metadata.feature_schema_version == FEATURE_SCHEMA_VERSION
    assert metadata.model_version == MODEL_VERSION
    assert metadata.dataset_version == DATASET_VERSION
    assert bundle["model"] is not None
    assert hasattr(bundle["model"], "predict_proba")


def test_prediction_repeatability(tmp_path: Path) -> None:
    paths = _train_and_evaluate(tmp_path)
    bundle_a = joblib.load(paths["artifact"])
    bundle_b = joblib.load(paths["artifact"])
    frame, _ = load_training_frame(csv_path=paths["csv"], summary_path=paths["summary"])
    sample = predictive_frame(split_frame(frame, split_name="test")).head(30)
    preds_a = bundle_a["model"].predict_proba(sample[list(FEATURE_COLUMNS)])[:, 1]
    preds_b = bundle_b["model"].predict_proba(sample[list(FEATURE_COLUMNS)])[:, 1]
    np.testing.assert_allclose(preds_a, preds_b, rtol=0, atol=1e-12)


def test_prediction_probabilities_are_valid(tmp_path: Path) -> None:
    paths = _train_and_evaluate(tmp_path)
    pipeline = joblib.load(paths["artifact"])["model"]
    frame, _ = load_training_frame(csv_path=paths["csv"], summary_path=paths["summary"])
    sample = predictive_frame(split_frame(frame, split_name="test"))
    probabilities = pipeline.predict_proba(sample[list(FEATURE_COLUMNS)])[:, 1]
    assert np.isfinite(probabilities).all()
    assert (probabilities >= 0).all()
    assert (probabilities <= 1).all()


def test_split_membership_discipline(tmp_path: Path) -> None:
    paths = _train_and_evaluate(tmp_path)
    frame, _ = load_training_frame(csv_path=paths["csv"], summary_path=paths["summary"])
    pipeline = fit_baseline_model(frame=frame, seed=DEFAULT_SEED)
    train_ids = set(split_frame(frame, split_name="train")["case_id"])
    valid_ids = set(split_frame(frame, split_name="validation")["case_id"])
    test_ids = set(split_frame(frame, split_name="test")["case_id"])
    assert train_ids.isdisjoint(valid_ids)
    assert train_ids.isdisjoint(test_ids)
    assert valid_ids.isdisjoint(test_ids)
    assert len(predictive_frame(split_frame(frame, split_name="train"))) > 0
    _ = pipeline


def test_metrics_json_required_sections(tmp_path: Path) -> None:
    paths = _train_and_evaluate(tmp_path)
    metrics = json.loads(paths["metrics"].read_text(encoding="utf-8"))
    for split in ("validation", "test"):
        section = metrics[split]
        for key in ("roc_auc", "pr_auc", "log_loss", "brier_score", "calibration_bins"):
            assert key in section
        assert np.isfinite(section["roc_auc"])
        assert np.isfinite(section["pr_auc"])
        assert np.isfinite(section["log_loss"])
        assert np.isfinite(section["brier_score"])
    assert "synthetic_policy_simulation" in metrics
    simulation = metrics["synthetic_policy_simulation"]
    assert simulation["evaluation_label"] == "SYNTHETIC POLICY SIMULATION"
    for policy_key in ("revloop_model_policy", "naive_baseline_policy"):
        policy = simulation[policy_key]
        for metric in (
            "number_of_cases",
            "amount_at_risk_minor",
            "expected_synthetic_recovered_minor",
            "realized_synthetic_recovered_minor",
            "realized_recovery_rate",
            "selected_intervention_count",
            "contact_action_count",
            "stop_count",
            "no_selection_count",
        ):
            assert metric in policy


def test_artifact_and_dataset_lineage_hashes(tmp_path: Path) -> None:
    paths = _train_and_evaluate(tmp_path)
    sidecar = json.loads(paths["metadata"].read_text(encoding="utf-8"))
    artifact_hash = hashlib.sha256(paths["artifact"].read_bytes()).hexdigest()
    csv_hash = hashlib.sha256(paths["csv"].read_bytes()).hexdigest()
    summary_hash = hashlib.sha256(paths["summary"].read_bytes()).hexdigest()
    assert sidecar["artifact_sha256"] == artifact_hash
    assert sidecar["training_data_sha256"] == csv_hash
    assert sidecar["summary_sha256"] == summary_hash
    assert sidecar["training_seed"] == DEFAULT_SEED
    assert sidecar["split_seed"] == DEFAULT_SEED + 3


def test_stop_probability_fixed_in_policy_simulation(tmp_path: Path) -> None:
    paths = _train_and_evaluate(tmp_path)
    bundle = joblib.load(paths["artifact"])
    assert bundle["metadata"]["deterministic_action_probabilities"]["STOP"] == 0.0
    metrics = json.loads(paths["metrics"].read_text(encoding="utf-8"))
    label = metrics["synthetic_policy_simulation"]["evaluation_label"]
    assert label == "SYNTHETIC POLICY SIMULATION"


def test_invalid_dataset_manifest_rejected(tmp_path: Path) -> None:
    csv_path, summary_path = _prepare_dataset(tmp_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["feature_schema_version"] = "wrong"
    bad_summary = tmp_path / "bad_summary.json"
    bad_summary.write_text(json.dumps(summary), encoding="utf-8")
    with pytest.raises(ValueError, match="feature_schema_version"):
        load_training_frame(csv_path=csv_path, summary_path=bad_summary)


def test_duplicate_csv_header_rejected(tmp_path: Path) -> None:
    from ml.common import validate_raw_csv_header

    header = list(CSV_COLUMNS)
    header[1] = "case_id"
    with pytest.raises(ValueError, match="Duplicate"):
        validate_raw_csv_header(header)
