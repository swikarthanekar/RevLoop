"""Response contracts for the demo-only endpoints (API_CONTRACTS.md section 12).

Field names deliberately mirror the canonical Prompt 11 synthetic-evaluation
vocabulary (``expected_synthetic_recovered_minor``,
``realized_synthetic_recovered_minor``, ``realized_recovery_rate``,
``selected_intervention_count``) rather than generic revenue names. Synthetic
simulation output must not read like real recovered revenue.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.demo.evaluation import SYNTHETIC_SIMULATION

#: The literal type pins the contract value so a typo cannot ship.
DataSource = Literal["SYNTHETIC_SIMULATION"]


class PolicySimulationSummary(BaseModel):
    """Per-policy synthetic metrics, exactly as the canonical evaluator reports."""

    model_config = ConfigDict(frozen=True)

    number_of_cases: int
    amount_at_risk_minor: int
    expected_synthetic_recovered_minor: int
    realized_synthetic_recovered_minor: int
    realized_recovery_rate: Decimal
    selected_intervention_count: int
    contact_action_count: int
    stop_count: int
    no_selection_count: int


class ScorerProvenanceModel(BaseModel):
    """Which model actually produced the probabilities behind these numbers."""

    model_config = ConfigDict(frozen=True, protected_namespaces=())

    model_version: str
    model_family: str
    feature_schema_version: str


class DatasetProvenanceModel(BaseModel):
    """Which synthetic world and cohort the evaluation ran against."""

    model_config = ConfigDict(frozen=True)

    dataset_version: str
    seed: int
    split: str
    case_count: int


class DemoBatchResponse(BaseModel):
    """Synthetic counterfactual comparison of RevLoop against the naive baseline."""

    model_config = ConfigDict(frozen=True)

    data_source: DataSource = SYNTHETIC_SIMULATION
    evaluation_label: str
    scorer: ScorerProvenanceModel
    dataset: DatasetProvenanceModel
    revloop_model_policy: PolicySimulationSummary
    naive_baseline_policy: PolicySimulationSummary
    incremental_expected_recovered_minor: int
    incremental_realized_recovered_minor: int


class DemoResetResponse(BaseModel):
    """Result of restoring the canonical deterministic demo baseline."""

    model_config = ConfigDict(frozen=True)

    data_source: DataSource = SYNTHETIC_SIMULATION
    seed_version: str
    reset_performed: bool
    organization_id: str
    recovery_case_count: int
    #: Externally provisioned `user_profiles` rows carried across the reset.
    #: Reported so an operator can see that hand-provisioned accounts (the
    #: signed-in demo user included) survived, rather than having to check by
    #: signing in again and hoping.
    preserved_user_profiles: int = 0


class DemoBatchCachedResponse(BaseModel):
    """A stored policy simulation, with the provenance of the run itself.

    `computed_at` and `duration_seconds` are shown to the reader on purpose. A
    number presented without saying when it was produced invites the assumption
    that it is a fixture; stating it, and offering a recompute, answers that
    before it is asked.
    """

    model_config = ConfigDict(frozen=True)

    evaluation: DemoBatchResponse
    computed_at: datetime
    duration_seconds: float
    #: True when this response triggered a fresh computation rather than
    #: reading the cache.
    recomputed: bool = False
