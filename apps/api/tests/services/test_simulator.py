"""Tests for the read-only recovery simulator.

The simulator's entire value rests on two claims: that it runs the production
decision path rather than an approximation of it, and that it cannot change
anything. Both are asserted here, because either failing quietly would turn an
honest demo into a misleading one.
"""

from __future__ import annotations

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.demo.constants import DEMO_ORGANIZATION_ID
from app.demo.seed import seed_demo_database
from app.domain.capabilities import is_executable
from app.domain.enums import CaseType, FailureCategory, RecoveryActionType
from app.schemas.simulator import SimulationRequest
from app.services.simulator import SimulationUnavailableError, simulate
from tests.demo.conftest import postgres_available, postgres_url

pytestmark = pytest.mark.skipif(
    not postgres_available(),
    reason="PostgreSQL not available (set REVLOOP_TEST_DATABASE_URL)",
)


@pytest.fixture(scope="module")
def simulator_db(migrated_postgres: Engine | None) -> Engine:
    if migrated_postgres is None:
        pytest.skip("PostgreSQL not available")
    url = postgres_url()
    assert url is not None
    seed_demo_database(
        reset=True,
        settings=Settings(
            app_env="test", demo_mode=True, database_url=url, _env_file=None
        ),
    )
    return migrated_postgres


@pytest.fixture()
def session(simulator_db: Engine):
    with sessionmaker(bind=simulator_db, future=True)() as db:
        yield db


def _score(session: Session, **overrides):
    payload = {
        "amount_minor": 199900,
        "failure_category": FailureCategory.AUTHENTICATION_FAILURE,
    }
    payload.update(overrides)
    return simulate(
        session,
        organization_id=DEMO_ORGANIZATION_ID,
        request=SimulationRequest(**payload),
    )


# --------------------------------------------------------------------------
# It runs the real engine
# --------------------------------------------------------------------------


def test_probabilities_come_from_the_real_model(session: Session) -> None:
    result = _score(session)
    assert result.model_version == "lr-v1.0.0"
    assert result.model_family == "logistic_regression"
    assert result.feature_schema_version == "recovery_features_v1"
    # `fallback` would mean a heuristic rule table produced these numbers while
    # the page attributes them to the model.
    assert result.inference_source == "model"


def test_erv_breakdown_reconciles_exactly(session: Session) -> None:
    """The waterfall must add up, or it is worse than showing nothing."""
    result = _score(session)
    assert result.candidates

    for candidate in result.candidates:
        net = (
            candidate.expected_recovered_minor
            - candidate.action_cost_minor
            - candidate.fatigue_penalty_minor
            - candidate.operational_risk_penalty_minor
            - candidate.delay_penalty_minor
        )
        assert net == candidate.expected_value_minor, candidate.action_type


def test_selection_is_capability_aware(session: Session) -> None:
    """The same rule as the live path: never select what cannot be executed."""
    result = _score(session)
    if result.selected_action is not None:
        assert is_executable(RecoveryActionType(result.selected_action))

    selected = [candidate for candidate in result.candidates if candidate.selected]
    assert len(selected) <= 1
    if selected:
        assert selected[0].action_type == result.selected_action


def test_advisory_rank_one_is_shown_but_not_selected(session: Session) -> None:
    """An authentication failure is where the model prefers retry.

    This is the scenario that makes the capability boundary visible, so it must
    keep behaving this way: retry ranked first, an executable action selected.
    """
    result = _score(session, amount_minor=199900)
    assert result.top_ranked_action == RecoveryActionType.RETRY_SAME_METHOD.value
    assert result.selected_action != result.top_ranked_action
    assert is_executable(RecoveryActionType(result.selected_action))

    advisory = next(
        candidate
        for candidate in result.candidates
        if candidate.action_type == RecoveryActionType.RETRY_SAME_METHOD.value
    )
    assert advisory.execution_mode == "ADVISORY"
    assert advisory.advisory_reason  # a reason, not a bare flag
    assert advisory.rank == 1  # still shown at its true rank


# --------------------------------------------------------------------------
# The controls actually drive the engine
# --------------------------------------------------------------------------


def test_amount_above_the_auto_limit_requires_approval(session: Session) -> None:
    """Dragging the amount past the merchant's limit must flip the verdict."""
    small = _score(session, amount_minor=199900)
    large = _score(session, amount_minor=5_000_000)

    small_selected = next(c for c in small.candidates if c.selected)
    large_selected = next(c for c in large.candidates if c.selected)

    assert small_selected.requires_approval is False
    assert large_selected.requires_approval is True
    assert "AMOUNT_ABOVE_AUTO_ACTION_LIMIT" in large_selected.policy_reasons
    assert large.amount_at_risk_minor > large.policy_auto_action_limit_minor


def test_rail_downtime_removes_retry_from_the_candidate_set(session: Session) -> None:
    """Candidate generation, not a UI filter, is what excludes retry."""
    degraded = _score(
        session,
        failure_category=FailureCategory.PAYMENT_RAIL_DOWNTIME,
        rail_degraded=True,
    )
    actions = {candidate.action_type for candidate in degraded.candidates}
    assert RecoveryActionType.RETRY_SAME_METHOD.value not in actions
    assert degraded.selected_action is not None


def test_subscription_scenarios_use_the_subscription_matrix(session: Session) -> None:
    result = _score(
        session,
        case_type=CaseType.SUBSCRIPTION_FAILURE,
        failure_category=FailureCategory.MANDATE_OR_RECURRING_FAILURE,
        subscription_status="halted",
    )
    actions = {candidate.action_type for candidate in result.candidates}
    # No subscription matrix contains RETRY_SAME_METHOD.
    assert RecoveryActionType.RETRY_SAME_METHOD.value not in actions


def test_identical_scenarios_score_identically(session: Session) -> None:
    """A slider the user did not touch must not change the answer."""
    first = _score(session)
    second = _score(session)
    assert [
        (c.action_type, c.rank, c.success_probability, c.expected_value_minor)
        for c in first.candidates
    ] == [
        (c.action_type, c.rank, c.success_probability, c.expected_value_minor)
        for c in second.candidates
    ]


# --------------------------------------------------------------------------
# It cannot change anything
# --------------------------------------------------------------------------


def test_simulation_writes_nothing(session: Session) -> None:
    """The property that makes this safe to hand to a stranger mid-demo."""
    from sqlalchemy import func, select

    from app.models.recovery_action import RecoveryAction
    from app.models.recovery_case import RecoveryCase
    from app.models.recovery_recommendation import RecoveryRecommendation

    def counts() -> tuple[int, int, int]:
        session.expire_all()
        return tuple(  # type: ignore[return-value]
            int(
                session.execute(
                    select(func.count()).select_from(model).where(
                        model.organization_id == DEMO_ORGANIZATION_ID
                    )
                ).scalar_one()
            )
            for model in (RecoveryCase, RecoveryRecommendation, RecoveryAction)
        )

    before = counts()
    for amount in (100_00, 500_00, 5_000_00, 50_000_00):
        _score(session, amount_minor=amount)
    assert counts() == before


def test_response_is_labelled_as_simulation(session: Session) -> None:
    """A client must not be able to present this as a real recovery."""
    assert _score(session).data_source == "INTERACTIVE_SIMULATION"


def test_scoring_fails_closed_without_the_real_model(session: Session) -> None:
    """No heuristic numbers under a page that credits the model."""
    from unittest.mock import patch

    from app.ml.service import ModelArtifactError

    with patch(
        "app.ml.service.RecoveryPropensityModelService.score_actions",
        side_effect=ModelArtifactError("simulated missing artifact"),
    ):
        with pytest.raises(SimulationUnavailableError) as excinfo:
            _score(session)
    assert excinfo.value.status_code == 503
    assert excinfo.value.code == "SIMULATION_UNAVAILABLE"


# --------------------------------------------------------------------------
# Input bounds
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"amount_minor": 0},
        {"amount_minor": 10_000_001_00},
        {"hours_since_failure": -1.0},
        {"hours_since_failure": 10_000.0},
        {"payment_success_rate_90d": 1.5},
    ],
)
def test_out_of_range_scenarios_are_rejected(overrides: dict) -> None:
    """Outside the training range a probability is extrapolation, not prediction."""
    from pydantic import ValidationError

    payload = {
        "amount_minor": 199900,
        "failure_category": FailureCategory.AUTHENTICATION_FAILURE,
    }
    payload.update(overrides)
    with pytest.raises(ValidationError):
        SimulationRequest(**payload)
