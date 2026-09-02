"""Trusted local recovery propensity model runtime service (Prompt 13)."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline

from app.core.config import Settings, get_settings
from app.domain.enums import RecoveryActionType
from app.ml.schemas import ActionProbability, ModelBundleMetadata, ModelInferenceResult
from app.recovery.schemas import FEATURE_SCHEMA_VERSION, RecoveryFeaturesV1

logger = logging.getLogger(__name__)

ARTIFACT_FORMAT_VERSION = "revloop-model-bundle-v1"


class ModelArtifactError(Exception):
    """Raised when a trusted local artifact fails validation."""


class ModelInferenceError(Exception):
    """Raised when model inference fails for a supported action."""


@dataclass(frozen=True)
class LoadedModelBundle:
    pipeline: Pipeline
    metadata: ModelBundleMetadata
    artifact_path: Path
    artifact_sha256: str


def resolve_trusted_model_bundle_path(settings: Settings) -> Path:
    configured = settings.model_bundle_path
    if configured.is_file():
        return configured
    canonical = Path(__file__).resolve().parent / "artifacts" / "recovery_model.joblib"
    if canonical.is_file():
        return canonical
    return configured


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _features_to_model_row(
    features: RecoveryFeaturesV1,
    action: RecoveryActionType,
) -> dict[str, Any]:
    return {
        "amount_log1p": features.amount_log1p,
        "customer_tenure_days": (
            None if features.customer_tenure_days_missing else features.customer_tenure_days
        ),
        "successful_payments_90d": (
            None if features.successful_payments_90d_missing else features.successful_payments_90d
        ),
        "failed_payments_30d": (
            None if features.failed_payments_30d_missing else features.failed_payments_30d
        ),
        "payment_success_rate_90d": (
            None if features.payment_success_rate_90d_missing else features.payment_success_rate_90d
        ),
        "historical_recovery_rate": (
            None if features.historical_recovery_rate_missing else features.historical_recovery_rate
        ),
        "lifetime_value_log1p": features.lifetime_value_log1p,
        "hours_since_failure": features.hours_since_failure,
        "retry_count_provider": (
            None if features.retry_count_provider_missing else features.retry_count_provider
        ),
        "recovery_attempts_so_far": features.recovery_attempts_so_far,
        "contacts_last_24h": features.contacts_last_24h,
        "rail_degraded": features.rail_degraded,
        "same_method_recent_success": features.same_method_recent_success,
        "alternate_method_recent_success": features.alternate_method_recent_success,
        "is_subscription": features.is_subscription,
        "case_type": features.case_type,
        "failure_category": features.failure_category,
        "payment_method": features.payment_method,
        "customer_segment": features.customer_segment,
        "downtime_severity": features.downtime_severity,
        "action_type": action.value,
    }


def _validate_loaded_bundle(
    *,
    bundle: dict[str, Any],
    artifact_path: Path,
    artifact_sha256: str,
) -> ModelBundleMetadata:
    if not isinstance(bundle, dict) or "model" not in bundle or "metadata" not in bundle:
        raise ModelArtifactError("Artifact bundle must contain model and metadata.")
    if not isinstance(bundle["model"], Pipeline):
        raise ModelArtifactError("Artifact model must be a sklearn Pipeline.")

    metadata = ModelBundleMetadata.model_validate(bundle["metadata"])
    if metadata.artifact_format_version != ARTIFACT_FORMAT_VERSION:
        raise ModelArtifactError(
            f"Unsupported artifact_format_version: {metadata.artifact_format_version}"
        )
    if metadata.feature_schema_version != FEATURE_SCHEMA_VERSION:
        raise ModelArtifactError(
            f"Unsupported feature_schema_version: {metadata.feature_schema_version}"
        )
    if metadata.artifact_sha256 is not None and metadata.artifact_sha256 != artifact_sha256:
        raise ModelArtifactError("Artifact SHA-256 mismatch between metadata and file bytes.")
    if metadata.model_family != "logistic_regression":
        raise ModelArtifactError(
            "Runtime artifact model_family must be logistic_regression, "
            f"got {metadata.model_family}."
        )
    return metadata


def _sidecar_metadata_path(artifact_path: Path) -> Path:
    return artifact_path.with_name(f"{artifact_path.stem}.metadata.json")


def _validate_artifact_bytes_against_sidecar(
    artifact_path: Path,
    artifact_sha256: str,
) -> None:
    sidecar_path = _sidecar_metadata_path(artifact_path)
    if not sidecar_path.is_file():
        return
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    expected = sidecar.get("artifact_sha256")
    if expected and expected != artifact_sha256:
        raise ModelArtifactError(
            "Artifact SHA-256 mismatch between sidecar metadata and file bytes."
        )


def load_trusted_model_bundle(settings: Settings | None = None) -> LoadedModelBundle:
    resolved_settings = settings or get_settings()
    artifact_path = resolve_trusted_model_bundle_path(resolved_settings)
    if not artifact_path.is_file():
        raise ModelArtifactError(f"Trusted model artifact not found: {artifact_path}")

    artifact_sha256 = sha256_file(artifact_path)
    _validate_artifact_bytes_against_sidecar(artifact_path, artifact_sha256)
    raw_bundle = joblib.load(artifact_path)
    metadata = _validate_loaded_bundle(
        bundle=raw_bundle,
        artifact_path=artifact_path,
        artifact_sha256=artifact_sha256,
    )
    return LoadedModelBundle(
        pipeline=raw_bundle["model"],
        metadata=metadata,
        artifact_path=artifact_path,
        artifact_sha256=artifact_sha256,
    )


@lru_cache
def get_loaded_model_bundle() -> LoadedModelBundle:
    return load_trusted_model_bundle()


class RecoveryPropensityModelService:
    """Scores recovery propensity for candidate actions only."""

    def __init__(self, bundle: LoadedModelBundle | None = None) -> None:
        self._bundle = bundle

    @property
    def bundle(self) -> LoadedModelBundle:
        if self._bundle is None:
            self._bundle = get_loaded_model_bundle()
        return self._bundle

    @property
    def model_version(self) -> str:
        return self.bundle.metadata.model_version

    @property
    def feature_schema_version(self) -> str:
        return self.bundle.metadata.feature_schema_version

    @property
    def model_family(self) -> str:
        return self.bundle.metadata.model_family

    @property
    def artifact_sha256(self) -> str:
        return self.bundle.artifact_sha256

    def score_actions(
        self,
        *,
        features: RecoveryFeaturesV1,
        actions: list[RecoveryActionType],
    ) -> ModelInferenceResult:
        if features.feature_schema_version != FEATURE_SCHEMA_VERSION:
            raise ModelInferenceError(
                f"Unsupported feature schema version: {features.feature_schema_version}"
            )

        metadata = self.bundle.metadata
        allowed_actions = {RecoveryActionType(value) for value in metadata.action_types}
        deterministic = metadata.deterministic_action_probabilities

        scored: list[ActionProbability] = []
        model_rows: list[dict[str, Any]] = []
        model_actions: list[RecoveryActionType] = []

        for action in actions:
            if action not in allowed_actions and action != RecoveryActionType.STOP:
                raise ModelInferenceError(f"Action not supported by artifact: {action.value}")
            if action == RecoveryActionType.STOP or action.value in deterministic:
                probability = float(deterministic.get(action.value, 0.0))
                scored.append(ActionProbability(action_type=action, probability=probability))
                continue
            model_rows.append(_features_to_model_row(features, action))
            model_actions.append(action)

        if model_rows:
            frame = pd.DataFrame(model_rows)
            for column in metadata.boolean_feature_columns:
                if column in frame.columns:
                    frame[column] = frame[column].astype(int)
            feature_columns = list(metadata.feature_columns)
            probabilities = self.bundle.pipeline.predict_proba(frame[feature_columns])[:, 1]
            if not np.isfinite(probabilities).all():
                raise ModelInferenceError("Model produced non-finite probabilities.")
            if ((probabilities < 0) | (probabilities > 1)).any():
                raise ModelInferenceError("Model produced probabilities outside [0, 1].")
            for action, probability in zip(model_actions, probabilities, strict=True):
                scored.append(
                    ActionProbability(action_type=action, probability=float(probability))
                )

        return ModelInferenceResult(
            model_version=self.model_version,
            model_family=self.model_family,
            feature_schema_version=self.feature_schema_version,
            artifact_sha256=self.artifact_sha256,
            source="model",
            fallback_reason=None,
            probabilities=tuple(scored),
        )


def clear_model_bundle_cache() -> None:
    get_loaded_model_bundle.cache_clear()
