"""The seeded demo dataset must leave every reachable control in a working state.

WHY THIS FILE EXISTS

936 tests passed while the deployed demo's primary call-to-action failed on 15
of the 16 cases that rendered it. Every unit was correct in isolation: candidate
generation, ranking, ERV, the policy engine, the executor's guard, and the UI's
control gating each did exactly what their own tests asserted. What no test
asserted was the property that actually matters to someone clicking around --
that the *dataset the demo actually ships* drives those correct units into a
working combination.

These tests assert that end-to-end property against the real seeded rows. They
are deliberately written in terms of what a user can reach and press, not in
terms of internal correctness, because internal correctness was never the thing
that broke.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.demo.constants import CASE_STATE_COUNTS, DEMO_ORGANIZATION_ID, RECOVERY_CASE_COUNT
from app.demo.seed import seed_demo_database
from app.domain.capabilities import EXECUTABLE_ACTION_TYPES, is_executable
from app.domain.enums import RecoveryActionStatus, RecoveryActionType, RecoveryCaseStatus
from app.models.recovery_action import RecoveryAction
from app.models.recovery_case import RecoveryCase
from app.models.recovery_recommendation import RecoveryRecommendation
from app.recovery.selection import select_candidate_row, top_ranked_row
from tests.demo.conftest import postgres_available, postgres_url

pytestmark = pytest.mark.skipif(
    not postgres_available(),
    reason="PostgreSQL not available (set REVLOOP_TEST_DATABASE_URL)",
)

#: Statuses whose case detail renders an enabled primary control.
#: `RECOMMENDED` renders "Execute recovery"; `AWAITING_APPROVAL` renders
#: "Approve action"; `DETECTED` renders "Analyze case". Mirrors
#: `getCaseControls` in apps/web/app/(app)/recovery/[caseId]/case-presentation.ts.
STATUSES_WITH_A_PRIMARY_CONTROL = (
    RecoveryCaseStatus.DETECTED.value,
    RecoveryCaseStatus.RECOMMENDED.value,
    RecoveryCaseStatus.AWAITING_APPROVAL.value,
)


@pytest.fixture(scope="module")
def seeded(migrated_postgres: Engine | None) -> Engine:
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
def session(seeded: Engine):
    with sessionmaker(bind=seeded, future=True)() as db:
        yield db


def _cases(db: Session, status: str) -> list[RecoveryCase]:
    return list(
        db.execute(
            select(RecoveryCase).where(
                RecoveryCase.organization_id == DEMO_ORGANIZATION_ID,
                RecoveryCase.status == status,
            )
        ).scalars()
    )


def _recommendations(db: Session, case: RecoveryCase) -> list[RecoveryRecommendation]:
    return list(
        db.execute(
            select(RecoveryRecommendation).where(
                RecoveryRecommendation.organization_id == DEMO_ORGANIZATION_ID,
                RecoveryRecommendation.case_id == case.id,
                RecoveryRecommendation.analysis_run_id == case.current_analysis_run_id,
            )
        ).scalars()
    )


# --------------------------------------------------------------------------
# The defect this file is named for
# --------------------------------------------------------------------------


def test_every_execute_button_targets_an_executable_action(session: Session) -> None:
    """THE regression. Pressing Execute must never hit ACTION_NOT_EXECUTABLE.

    A `RECOMMENDED` case renders an enabled "Execute recovery" button wired to
    the analysis's selected action. If that action is advisory, the click
    returns `422` and the user has no way forward.
    """
    cases = _cases(session, RecoveryCaseStatus.RECOMMENDED.value)
    assert cases, "no RECOMMENDED cases: this test would vacuously pass"

    broken = []
    for case in cases:
        recommendations = _recommendations(session, case)
        assert recommendations, f"case {case.id} is RECOMMENDED with no recommendations"
        selected = select_candidate_row(recommendations)
        if selected is None or not is_executable(RecoveryActionType(selected.action_type)):
            broken.append((case.id, selected.action_type if selected else None))

    assert not broken, (
        "Execute would fail with 422 ACTION_NOT_EXECUTABLE on these cases: " f"{broken}"
    )


def test_every_analysed_case_has_an_executable_selection(session: Session) -> None:
    """Not only the ones currently rendering a button.

    A case can transition into `RECOMMENDED` later; the invariant should hold
    for every analysed case, so a state change cannot create a broken control.
    """
    cases = list(
        session.execute(
            select(RecoveryCase).where(
                RecoveryCase.organization_id == DEMO_ORGANIZATION_ID,
                RecoveryCase.current_analysis_run_id.is_not(None),
            )
        ).scalars()
    )
    assert cases

    for case in cases:
        selected = select_candidate_row(_recommendations(session, case))
        assert selected is not None, f"case {case.id} has an analysis but no selection"
        assert is_executable(RecoveryActionType(selected.action_type)), (
            f"case {case.id} selected advisory action {selected.action_type}"
        )


def test_seeded_action_history_contains_only_executable_actions(session: Session) -> None:
    """Recorded history must not claim RevLoop performed something it cannot.

    The dashboard's action-effectiveness panel aggregates these rows. Seeding
    them from rank 1 rather than the selected action credited most recovered
    revenue to `RETRY_SAME_METHOD`, an action the product never executes.
    """
    actions = list(
        session.execute(
            select(RecoveryAction).where(
                RecoveryAction.organization_id == DEMO_ORGANIZATION_ID
            )
        ).scalars()
    )
    assert actions

    offenders = sorted(
        {
            action.action_type
            for action in actions
            if not is_executable(RecoveryActionType(action.action_type))
        }
    )
    assert not offenders, (
        "seeded history records actions RevLoop cannot execute: " f"{offenders}"
    )


# --------------------------------------------------------------------------
# Every state a control depends on must be reachable and coherent
# --------------------------------------------------------------------------


def test_analyze_flow_is_demonstrable(session: Session) -> None:
    """At least one DETECTED case, or the Analyze button cannot be shown at all.

    This is the state the audit consumed entirely; with zero DETECTED cases the
    analyze step simply could not be demonstrated.
    """
    detected = _cases(session, RecoveryCaseStatus.DETECTED.value)
    assert detected, "no DETECTED case: the Analyze control is unreachable"
    assert len(detected) == CASE_STATE_COUNTS[RecoveryCaseStatus.DETECTED.value]
    for case in detected:
        assert case.current_analysis_run_id is None, (
            "a DETECTED case must not already carry an analysis"
        )


def test_approval_flow_is_demonstrable(session: Session) -> None:
    """Every AWAITING_APPROVAL case must have the action it is waiting on.

    The UI's `canApprove` requires a non-null latest action. Seeding produced
    none, so all five approval cases rendered explanatory text and two Refresh
    buttons, with no way to progress -- a headline capability with no reachable
    surface.
    """
    cases = _cases(session, RecoveryCaseStatus.AWAITING_APPROVAL.value)
    assert cases, "no AWAITING_APPROVAL cases"

    for case in cases:
        action = session.execute(
            select(RecoveryAction).where(
                RecoveryAction.organization_id == DEMO_ORGANIZATION_ID,
                RecoveryAction.case_id == case.id,
            )
        ).scalars().first()
        assert action is not None, (
            f"case {case.id} is AWAITING_APPROVAL with no action to approve"
        )
        assert action.status == RecoveryActionStatus.PENDING_APPROVAL.value
        assert action.requires_approval is True
        # Not yet approved, so these must be empty -- otherwise the row claims
        # an approval that never happened.
        assert action.approved_by is None
        assert action.approved_at is None
        assert is_executable(RecoveryActionType(action.action_type))


def test_case_state_distribution_matches_the_canonical_plan(session: Session) -> None:
    """Guards against a seed change quietly emptying a demonstrable state."""
    rows = dict(
        session.execute(
            select(RecoveryCase.status, __import__("sqlalchemy").func.count())
            .where(RecoveryCase.organization_id == DEMO_ORGANIZATION_ID)
            .group_by(RecoveryCase.status)
        ).all()
    )
    assert rows == CASE_STATE_COUNTS
    assert sum(rows.values()) == RECOVERY_CASE_COUNT
    for status in STATUSES_WITH_A_PRIMARY_CONTROL:
        assert rows.get(status, 0) > 0, f"no case in {status}: its control is unreachable"


# --------------------------------------------------------------------------
# Credibility of what the seeded rows display
# --------------------------------------------------------------------------


def test_seeded_analyses_come_from_the_real_model(session: Session) -> None:
    """No canned heuristic rows under an "AI RECOVERY DECISION" heading."""
    versions = set(
        session.execute(
            select(RecoveryRecommendation.model_version).where(
                RecoveryRecommendation.organization_id == DEMO_ORGANIZATION_ID
            )
        ).scalars()
    )
    assert versions == {"lr-v1.0.0"}, f"expected only the real model, got {versions}"

    schemas = set(
        session.execute(
            select(RecoveryRecommendation.feature_schema_version).where(
                RecoveryRecommendation.organization_id == DEMO_ORGANIZATION_ID
            )
        ).scalars()
    )
    assert schemas == {"recovery_features_v1"}


def test_expected_value_is_net_of_action_cost(session: Session) -> None:
    """Expected value and expected recovery must not print the same number.

    They were identical on 94 of 100 seeded cases because the canned rows never
    subtracted action cost -- visibly wrong to anyone reading both fields.
    """
    rows = list(
        session.execute(
            select(RecoveryRecommendation).where(
                RecoveryRecommendation.organization_id == DEMO_ORGANIZATION_ID,
                RecoveryRecommendation.action_type != RecoveryActionType.STOP.value,
            )
        ).scalars()
    )
    assert rows

    identical = [
        row.id
        for row in rows
        if int(row.expected_recovered_minor) == int(row.expected_value_minor)
    ]
    assert not identical, (
        f"{len(identical)} recommendations report expected value equal to expected "
        "recovery, so action cost was never subtracted"
    )
    for row in rows:
        assert int(row.expected_value_minor) < int(row.expected_recovered_minor)


def test_recovery_latency_is_not_a_single_constant(session: Session) -> None:
    """Avg. time to recover must not render as a suspiciously exact `1d`."""
    values = [
        row
        for row in session.execute(
            select(RecoveryCase.id).where(
                RecoveryCase.organization_id == DEMO_ORGANIZATION_ID
            )
        ).scalars()
    ]
    assert values

    from app.models.recovery_outcome import RecoveryOutcome

    latencies = [
        int(value)
        for value in session.execute(
            select(RecoveryOutcome.time_to_recovery_seconds).where(
                RecoveryOutcome.organization_id == DEMO_ORGANIZATION_ID,
                RecoveryOutcome.time_to_recovery_seconds.is_not(None),
            )
        ).scalars()
    ]
    assert latencies, "no recovered outcomes carry a latency"
    assert len(set(latencies)) > 1, "every recovered case shares one hardcoded latency"
    assert 86400 not in set(latencies) or len(set(latencies)) > 5


def test_the_model_preference_is_still_visible_where_it_differs(session: Session) -> None:
    """Capability-aware selection must narrow selection, never hide candidates.

    If advisory actions had simply been dropped from generation, the demo would
    no longer show what the model actually preferred. At least one seeded case
    should rank an advisory action first while selecting an executable one --
    that divergence is the honest, and most interesting, thing to show.
    """
    cases = list(
        session.execute(
            select(RecoveryCase).where(
                RecoveryCase.organization_id == DEMO_ORGANIZATION_ID,
                RecoveryCase.current_analysis_run_id.is_not(None),
            )
        ).scalars()
    )

    divergent = 0
    for case in cases:
        recommendations = _recommendations(session, case)
        top = top_ranked_row(recommendations)
        selected = select_candidate_row(recommendations)
        if top is None or selected is None:
            continue
        if top.action_type != selected.action_type:
            assert not is_executable(RecoveryActionType(top.action_type)) or (
                not top.policy_eligible
            ), (
                f"case {case.id} selected {selected.action_type} over an executable, "
                f"eligible rank 1 {top.action_type}"
            )
            divergent += 1

    assert divergent > 0, (
        "no seeded case shows the model preferring an action RevLoop does not "
        "execute; the advisory explanation would never be visible"
    )


def test_advisory_actions_still_appear_as_candidates(session: Session) -> None:
    """The model's real output stays on screen, it is just not selected."""
    action_types = set(
        session.execute(
            select(RecoveryRecommendation.action_type).where(
                RecoveryRecommendation.organization_id == DEMO_ORGANIZATION_ID
            )
        ).scalars()
    )
    advisory_present = {
        value for value in action_types if not is_executable(RecoveryActionType(value))
    }
    assert advisory_present, (
        "no advisory candidate survives in the seeded data, so the capability "
        "boundary is invisible rather than explained"
    )


def test_executable_set_matches_what_the_executor_enforces(session: Session) -> None:
    """One source of truth: selection and the executor must agree."""
    from app.actions.service import RecoveryActionService  # noqa: F401

    assert RecoveryActionType.RETRY_SAME_METHOD not in EXECUTABLE_ACTION_TYPES
    assert RecoveryActionType.SEND_RECOVERY_MESSAGE not in EXECUTABLE_ACTION_TYPES
    assert RecoveryActionType.CREATE_PAYMENT_LINK in EXECUTABLE_ACTION_TYPES
    assert RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD in EXECUTABLE_ACTION_TYPES


# --------------------------------------------------------------------------
# The ERV arithmetic must be exact wherever it is shown
# --------------------------------------------------------------------------


def test_every_seeded_recommendation_stores_its_erv_components(
    session: Session,
) -> None:
    """The waterfall is only honest if the parts were actually recorded.

    Recomputing them on read cannot be exact: the fatigue penalty depends on
    `contacts_last_24h` at the moment of analysis, which is not persisted. So
    the components are stored, and a reader that finds them missing must show
    nothing rather than reconstruct an approximation.
    """
    rows = list(
        session.execute(
            select(RecoveryRecommendation).where(
                RecoveryRecommendation.organization_id == DEMO_ORGANIZATION_ID
            )
        ).scalars()
    )
    assert rows

    for row in rows:
        assert row.erv_action_cost_minor is not None, row.id
        assert row.erv_fatigue_penalty_minor is not None, row.id
        assert row.erv_operational_risk_penalty_minor is not None, row.id
        assert row.erv_delay_penalty_minor is not None, row.id


def test_stored_erv_components_reconcile_with_the_stored_total(
    session: Session,
) -> None:
    """expected_recovered - every penalty == expected_value, on every row.

    A waterfall whose parts disagree with its total is worse than no waterfall,
    because it invites a reader to trust arithmetic that is wrong.
    """
    rows = list(
        session.execute(
            select(RecoveryRecommendation).where(
                RecoveryRecommendation.organization_id == DEMO_ORGANIZATION_ID
            )
        ).scalars()
    )
    assert rows

    mismatched = []
    for row in rows:
        net = (
            int(row.expected_recovered_minor)
            - int(row.erv_action_cost_minor)
            - int(row.erv_fatigue_penalty_minor)
            - int(row.erv_operational_risk_penalty_minor)
            - int(row.erv_delay_penalty_minor)
        )
        if net != int(row.expected_value_minor):
            mismatched.append((row.id, row.action_type, net, row.expected_value_minor))

    assert not mismatched, f"ERV components do not sum to the total: {mismatched}"


def test_read_path_withholds_a_breakdown_that_does_not_reconcile(
    session: Session,
) -> None:
    """The integrity guard, exercised rather than assumed.

    A row whose stored components disagree with its stored total must yield no
    breakdown at all. Silence is the correct failure mode here.
    """
    from app.services.recovery_case_service import _map_erv_breakdown

    row = session.execute(
        select(RecoveryRecommendation).where(
            RecoveryRecommendation.organization_id == DEMO_ORGANIZATION_ID
        )
    ).scalars().first()
    assert row is not None
    assert _map_erv_breakdown(row) is not None, "a healthy row should produce one"

    # Corrupt one component in memory only; the session is never flushed.
    original = row.erv_action_cost_minor
    try:
        row.erv_action_cost_minor = int(original) + 1
        assert _map_erv_breakdown(row) is None
    finally:
        row.erv_action_cost_minor = original
        session.expunge_all()


def test_read_path_withholds_a_breakdown_for_rows_written_before_m3r07(
    session: Session,
) -> None:
    """Older rows have no components, and must not get a reconstructed one."""
    from app.services.recovery_case_service import _map_erv_breakdown

    row = session.execute(
        select(RecoveryRecommendation).where(
            RecoveryRecommendation.organization_id == DEMO_ORGANIZATION_ID
        )
    ).scalars().first()
    assert row is not None

    original = row.erv_fatigue_penalty_minor
    try:
        row.erv_fatigue_penalty_minor = None
        assert _map_erv_breakdown(row) is None
    finally:
        row.erv_fatigue_penalty_minor = original
        session.expunge_all()
