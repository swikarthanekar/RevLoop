"""ML artifact metadata schemas (Prompt 11 — no runtime inference service yet)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import RecoveryActionType
from app.recovery.schemas import FEATURE_SCHEMA_VERSION


class ActionProbability(BaseModel):
    model_config = ConfigDict(frozen=True)

    action_type: RecoveryActionType
    probability: float = Field(ge=0.0, le=1.0)


class ModelInferenceResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    model_version: str
    model_family: str
    feature_schema_version: str
    artifact_sha256: str
    source: Literal["model", "fallback"]
    fallback_reason: str | None = None
    probabilities: tuple[ActionProbability, ...]


class ModelBundleMetadata(BaseModel):
    """Typed metadata for a trusted local recovery propensity model bundle."""

    model_config = ConfigDict(frozen=True)

    artifact_format_version: str
    model_version: str
    model_family: str
    feature_schema_version: str = FEATURE_SCHEMA_VERSION
    dataset_version: str
    training_seed: int
    split_seed: int
    training_case_count: int = Field(ge=0)
    training_row_count: int = Field(ge=0)
    validation_case_count: int = Field(ge=0)
    validation_row_count: int = Field(ge=0)
    feature_columns: tuple[str, ...]
    numeric_feature_columns: tuple[str, ...]
    boolean_feature_columns: tuple[str, ...]
    categorical_feature_columns: tuple[str, ...]
    action_types: tuple[str, ...]
    deterministic_action_probabilities: dict[str, float]
    training_configuration: dict[str, Any]
    library_versions: dict[str, str]
    validation_metrics: dict[str, Any]
    training_data_sha256: str
    summary_sha256: str
    artifact_sha256: str | None = None
    artifact_file: str | None = None
    trained_at: str | None = None
