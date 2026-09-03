"""Prompt 24 — P0 integration proof.

Every assertion goes through a public boundary: the signed webhook HTTP
endpoint, the analysis/action/approval REST API, and the timeline and dashboard
reads. After the qualifying failure event the test never writes business rows
itself, so the case, analysis, action and outcome are all produced by real
application paths.

Module configuration: the LLM is disabled (no Gemini key) and Razorpay API
credentials stay at their `dev-` defaults, so the deterministic engine carries
the flow and the only provider traffic is payment-link creation through an
injected mock transport.

Each test gets its own customer. Recovery features include the customer's recent
history, so a shared customer would let earlier tests shift later
recommendations. With a fresh customer the engine deterministically selects
CREATE_PAYMENT_LINK and requires approval (`CONFIDENCE_BELOW_AUTO_THRESHOLD`),
so the flow exercises the real ADMIN approval path.
"""

from __future__ import annotations

import uuid

import httpx
from sqlalchemy import func, select

from app.core.auth import AuthContext, get_current_user
from app.demo.constants import DEMO_ORGANIZATION_ID
from app.domain.enums import (
    RecoveryActionStatus,
    RecoveryActionType,
    RecoveryCaseStatus,
    UserRole,
)
from app.models.recovery_action import RecoveryAction
from app.models.recovery_case import RecoveryCase
from app.models.recovery_outcome import RecoveryOutcome
from app.models.recovery_recommendation import RecoveryRecommendation
from app.models.webhook_event import WebhookEvent
from app.services.provider_events import payment_failed_source_event_key
from tests.integration.conftest import ADMIN_HEADERS, ANALYST_HEADERS, OPERATOR_HEADERS
from tests.integration.helpers import (
    DEFAULT_AMOUNT_MINOR,
    SENSITIVE_SENTINEL,
    dashboard_recovered_minor,
    failure_payload,
    payment_link_paid_payload,
    post_webhook,
)


def unique_suffix() -> str:
    """Unique provider identifiers so tests never collide in a shared database."""
    return uuid.uuid4().hex[:12]


def load_case(session, payment_id: str) -> RecoveryCase:
    return session.execute(
        select(RecoveryCase).where(
            RecoveryCase.source_event_key == payment_failed_source_event_key(payment_id)
        )
    ).scalar_one()


def count_cases(session, payment_id: str) -> int:
    return int(
        session.execute(
            select(func.count())
            .select_from(RecoveryCase)
            .where(
                RecoveryCase.source_event_key == payment_failed_source_event_key(payment_id)
            )
        ).scalar_one()
    )


def count_outcomes(session, case_id) -> int:
    return int(
        session.execute(
            select(func.count())
            .select_from(RecoveryOutcome)
            .where(RecoveryOutcome.case_id == case_id)
        ).scalar_one()
    )


def case_actions(session, case_id) -> list[RecoveryAction]:
    return list(
        session.execute(
            select(RecoveryAction).where(RecoveryAction.case_id == case_id)
        ).scalars()
    )


def timeline_event_types(client, case_id) -> list[str]:
    response = client.get(f"/api/v1/recovery-cases/{case_id}/timeline", headers=ANALYST_HEADERS)
    assert response.status_code == 200, response.text
    return [item["event_type"] for item in response.json()["items"]]


def open_case(client, db_session, *, payment_id: str, customer_external_id: str, suffix: str):
    """Post a qualifying failure event and return the created case id."""
    response = post_webhook(
        client,
        failure_payload(payment_id=payment_id, customer_external_id=customer_external_id),
        event_id=f"evt_fail_{suffix}",
    )
    assert response.status_code == 204, response.text
    return load_case(db_session, payment_id).id


def drive_to_waiting_for_outcome(client, db_session, case_id) -> RecoveryAction:
    """Analyze, create the recommended action, approve if the policy demands it.

    Whichever approval semantics apply are honored rather than bypassed.
    """
    analysis = client.post(
        f"/api/v1/recovery-cases/{case_id}/analyze",
        headers=ANALYST_HEADERS,
        json={"reason": "MANUAL_ANALYSIS"},
    )
    assert analysis.status_code == 200, analysis.text
    body = analysis.json()

    create = client.post(
        f"/api/v1/recovery-cases/{case_id}/actions",
        headers=OPERATOR_HEADERS,
        json={
            "analysis_run_id": body["analysis_run_id"],
            "action_type": body["selected"]["action_type"],
        },
    )
    assert create.status_code == 201, create.text

    if create.json()["case_status"] == RecoveryCaseStatus.AWAITING_APPROVAL.value:
        db_session.expire_all()
        approve = client.post(
            f"/api/v1/recovery-actions/{create.json()['action']['id']}/approve",
            headers=ADMIN_HEADERS,
            json={"expected_case_version": db_session.get(RecoveryCase, case_id).version},
        )
        assert approve.status_code == 200, approve.text

    db_session.expire_all()
    assert (
        db_session.get(RecoveryCase, case_id).status
        == RecoveryCaseStatus.WAITING_FOR_OUTCOME.value
    )
    return case_actions(db_session, case_id)[0]


# ---------------------------------------------------------------------------
# The required end-to-end proof
# ---------------------------------------------------------------------------


def test_complete_p0_recovery_flow_is_consistent_end_to_end(
    client, db_session, customer_external_id, provider_spy, monkeypatch
) -> None:
    """Failure webhook through to recovered revenue, with the LLM disabled."""
    suffix = unique_suffix()
    payment_id = f"pay_e2e_{suffix}"

    # Fail loud on real network or LLM construction. The mock Razorpay transport
    # is an httpx.MockTransport, so it never touches HTTPTransport.
    def blocked_network(*_args: object, **_kwargs: object):
        raise AssertionError("Integration flow must not perform real outbound HTTP.")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked_network)

    llm_calls: list[str] = []

    class ForbiddenLLM:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            llm_calls.append("constructed")
            raise AssertionError("LLM must not be constructed while disabled.")

    monkeypatch.setattr("app.ai.factory.GeminiLLMProvider", ForbiddenLLM)

    revenue_before = dashboard_recovered_minor(client, ANALYST_HEADERS)

    # --- 1. qualifying failure event through the real webhook boundary ------
    failure = post_webhook(
        client,
        failure_payload(payment_id=payment_id, customer_external_id=customer_external_id),
        event_id=f"evt_e2e_fail_{suffix}",
    )
    assert failure.status_code == 204

    # --- 2. exactly one recovery case, correctly scoped ---------------------
    assert count_cases(db_session, payment_id) == 1
    case = load_case(db_session, payment_id)
    case_id = case.id
    assert case.organization_id == DEMO_ORGANIZATION_ID
    assert case.status == RecoveryCaseStatus.DETECTED.value
    assert case.amount_at_risk_minor == DEFAULT_AMOUNT_MINOR
    assert case.currency == "INR"
    assert case.current_analysis_run_id is None

    # --- 3. analysis through the real API ----------------------------------
    analyze = client.post(
        f"/api/v1/recovery-cases/{case_id}/analyze",
        headers=ANALYST_HEADERS,
        json={"reason": "MANUAL_ANALYSIS"},
    )
    assert analyze.status_code == 200, analyze.text
    analysis = analyze.json()
    assert analysis["status"] == RecoveryCaseStatus.RECOMMENDED.value
    analysis_run_id = analysis["analysis_run_id"]
    selected = analysis["selected"]
    assert selected is not None

    # LLM disabled degrades the narrative only, never the decision.
    assert analysis["explanation_source"] == "TEMPLATE_FALLBACK"
    assert llm_calls == []

    # --- 4. persisted analysis carries the authoritative outputs ------------
    recommendations = list(
        db_session.execute(
            select(RecoveryRecommendation)
            .where(RecoveryRecommendation.analysis_run_id == uuid.UUID(analysis_run_id))
            .order_by(RecoveryRecommendation.rank)
        ).scalars()
    )
    assert len(recommendations) == len(analysis["candidates"])
    assert [r.rank for r in recommendations] == list(range(1, len(recommendations) + 1))
    for recommendation in recommendations:
        assert recommendation.organization_id == DEMO_ORGANIZATION_ID
        assert recommendation.case_id == case_id
        assert 0 <= float(recommendation.success_probability) <= 1
        assert recommendation.expected_recovered_minor >= 0
        assert isinstance(recommendation.policy_eligible, bool)
        assert isinstance(recommendation.policy_reasons, list)
        # Runtime scoring uses the frozen selected model, not the offline evaluator.
        assert recommendation.model_version == "lr-v1.0.0"
        assert recommendation.feature_schema_version == "recovery_features_v1"

    top = recommendations[0]
    assert top.action_type == selected["action_type"]

    # STOP semantics: a stop candidate carries no recoverable value.
    stop_rows = [
        r for r in recommendations if r.action_type == RecoveryActionType.STOP.value
    ]
    assert stop_rows, "STOP must remain a considered candidate"
    for stop_row in stop_rows:
        assert float(stop_row.success_probability) == 0.0
        assert stop_row.expected_recovered_minor == 0
        assert stop_row.expected_value_minor == 0

    db_session.expire_all()
    case = db_session.get(RecoveryCase, case_id)
    assert case.current_analysis_run_id == uuid.UUID(analysis_run_id)
    assert case.recovery_probability is not None
    assert case.expected_recoverable_minor == top.expected_recovered_minor

    assert selected["action_type"] == RecoveryActionType.CREATE_PAYMENT_LINK.value

    # --- 5. action creation through the real API ---------------------------
    create = client.post(
        f"/api/v1/recovery-cases/{case_id}/actions",
        headers=OPERATOR_HEADERS,
        json={
            "analysis_run_id": analysis_run_id,
            "action_type": selected["action_type"],
        },
    )
    assert create.status_code == 201, create.text
    created = create.json()

    actions = case_actions(db_session, case_id)
    assert len(actions) == 1
    action = actions[0]
    assert action.organization_id == DEMO_ORGANIZATION_ID
    assert action.action_type == RecoveryActionType.CREATE_PAYMENT_LINK.value

    # --- 6. approval is required for this fixture and must be honored ------
    assert selected["requires_approval"] is True
    assert "CONFIDENCE_BELOW_AUTO_THRESHOLD" in top.policy_reasons
    assert created["case_status"] == RecoveryCaseStatus.AWAITING_APPROVAL.value
    assert created["action"]["status"] == RecoveryActionStatus.PENDING_APPROVAL.value
    # Nothing was sent to the provider while approval was outstanding.
    assert provider_spy.post_count == 0

    db_session.expire_all()
    case = db_session.get(RecoveryCase, case_id)
    awaiting_version = case.version

    # A non-admin cannot approve.
    forbidden = client.post(
        f"/api/v1/recovery-actions/{action.id}/approve",
        headers=OPERATOR_HEADERS,
        json={"expected_case_version": awaiting_version},
    )
    assert forbidden.status_code == 403

    # A stale case version is rejected.
    stale = client.post(
        f"/api/v1/recovery-actions/{action.id}/approve",
        headers=ADMIN_HEADERS,
        json={"expected_case_version": awaiting_version - 1},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "STALE_CASE_VERSION"

    approve = client.post(
        f"/api/v1/recovery-actions/{action.id}/approve",
        headers=ADMIN_HEADERS,
        json={"expected_case_version": awaiting_version},
    )
    assert approve.status_code == 200, approve.text

    # --- 7. execution reached WAITING_FOR_OUTCOME through the adapter ------
    db_session.expire_all()
    action = db_session.get(RecoveryAction, action.id)
    assert action.provider_reference
    assert provider_spy.post_count == 1
    assert provider_spy.last_reference == action.provider_reference

    case = db_session.get(RecoveryCase, case_id)
    assert case.status == RecoveryCaseStatus.WAITING_FOR_OUTCOME.value
    # Sending a link is not recovery: no outcome may exist yet.
    assert count_outcomes(db_session, case_id) == 0

    # --- 8. verified success through the real webhook boundary -------------
    success = post_webhook(
        client,
        payment_link_paid_payload(
            reference_id=action.provider_reference,
            payment_id=f"pay_e2e_paid_{suffix}",
            amount_minor=DEFAULT_AMOUNT_MINOR,
        ),
        event_id=f"evt_e2e_paid_{suffix}",
    )
    assert success.status_code == 204

    db_session.expire_all()
    case = db_session.get(RecoveryCase, case_id)
    assert case.status == RecoveryCaseStatus.RECOVERED.value

    # --- 9. exactly one outcome, money owned by the workflow ---------------
    assert count_outcomes(db_session, case_id) == 1
    outcome = db_session.execute(
        select(RecoveryOutcome).where(RecoveryOutcome.case_id == case_id)
    ).scalar_one()
    assert outcome.outcome == "RECOVERED"
    assert outcome.recovered_amount_minor == DEFAULT_AMOUNT_MINOR
    assert outcome.organization_id == DEMO_ORGANIZATION_ID
    assert outcome.verification_source == "WEBHOOK"
    assert outcome.recovered_at is not None

    db_session.expire_all()
    action = db_session.get(RecoveryAction, action.id)
    assert action.status == RecoveryActionStatus.SUCCEEDED.value

    # --- 10. the public timeline reflects the real lifecycle ---------------
    assert timeline_event_types(client, case_id) == [
        "CASE_CREATED",
        "ANALYSIS_REQUESTED",
        "ANALYSIS_COMPLETED",
        "APPROVAL_REQUESTED",
        "ACTION_EXECUTION_STARTED",
        "ACTION_ACCEPTED_OR_UNKNOWN",
        "CASE_RECOVERED",
    ]

    # --- 11. dashboard revenue moved by exactly the recovered amount -------
    revenue_after = dashboard_recovered_minor(client, ANALYST_HEADERS)
    assert revenue_after - revenue_before == DEFAULT_AMOUNT_MINOR
    assert llm_calls == []


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_failure_event_replay_does_not_create_a_second_case(
    client, db_session, customer_external_id
) -> None:
    suffix = unique_suffix()
    payment_id = f"pay_replay_{suffix}"
    event_id = f"evt_replay_{suffix}"
    payload = failure_payload(
        payment_id=payment_id, customer_external_id=customer_external_id
    )

    assert post_webhook(client, payload, event_id=event_id).status_code == 204
    assert count_cases(db_session, payment_id) == 1

    assert post_webhook(client, payload, event_id=event_id).status_code == 204
    assert count_cases(db_session, payment_id) == 1

    webhook_events = int(
        db_session.execute(
            select(func.count())
            .select_from(WebhookEvent)
            .where(WebhookEvent.provider_event_id == event_id)
        ).scalar_one()
    )
    assert webhook_events == 1


def test_same_payment_under_a_new_event_id_does_not_duplicate_the_case(
    client, db_session, customer_external_id
) -> None:
    """Case identity is the payment, not the delivery attempt."""
    suffix = unique_suffix()
    payment_id = f"pay_redeliver_{suffix}"
    payload = failure_payload(
        payment_id=payment_id, customer_external_id=customer_external_id
    )

    assert post_webhook(client, payload, event_id=f"evt_a_{suffix}").status_code == 204
    assert post_webhook(client, payload, event_id=f"evt_b_{suffix}").status_code == 204
    assert count_cases(db_session, payment_id) == 1


def test_duplicate_action_request_does_not_create_a_second_action(
    client, db_session, customer_external_id, provider_spy
) -> None:
    """The existing idempotent-create contract: one action, one provider call."""
    suffix = unique_suffix()
    case_id = open_case(
        client,
        db_session,
        payment_id=f"pay_dupaction_{suffix}",
        customer_external_id=customer_external_id,
        suffix=suffix,
    )

    analysis = client.post(
        f"/api/v1/recovery-cases/{case_id}/analyze",
        headers=ANALYST_HEADERS,
        json={"reason": "MANUAL_ANALYSIS"},
    ).json()
    request_body = {
        "analysis_run_id": analysis["analysis_run_id"],
        "action_type": analysis["selected"]["action_type"],
    }

    first = client.post(
        f"/api/v1/recovery-cases/{case_id}/actions",
        headers=OPERATOR_HEADERS,
        json=request_body,
    )
    assert first.status_code == 201, first.text

    second = client.post(
        f"/api/v1/recovery-cases/{case_id}/actions",
        headers=OPERATOR_HEADERS,
        json=request_body,
    )
    assert second.status_code == 201, second.text
    assert second.json()["action"]["id"] == first.json()["action"]["id"]

    assert len(case_actions(db_session, case_id)) == 1
    # Approval is still outstanding, so nothing reached the provider twice.
    assert provider_spy.post_count == 0


def test_success_replay_does_not_duplicate_outcome_or_dashboard_revenue(
    client, db_session, customer_external_id, provider_spy
) -> None:
    """Webhook idempotency, outcome idempotency and analytics correctness."""
    suffix = unique_suffix()
    case_id = open_case(
        client,
        db_session,
        payment_id=f"pay_sreplay_{suffix}",
        customer_external_id=customer_external_id,
        suffix=suffix,
    )
    action = drive_to_waiting_for_outcome(client, db_session, case_id)

    revenue_before = dashboard_recovered_minor(client, ANALYST_HEADERS)

    success_payload = payment_link_paid_payload(
        reference_id=action.provider_reference,
        payment_id=f"pay_sreplay_paid_{suffix}",
        amount_minor=DEFAULT_AMOUNT_MINOR,
    )
    event_id = f"evt_sr_paid_{suffix}"

    assert post_webhook(client, success_payload, event_id=event_id).status_code == 204
    db_session.expire_all()
    assert db_session.get(RecoveryCase, case_id).status == RecoveryCaseStatus.RECOVERED.value
    assert count_outcomes(db_session, case_id) == 1
    revenue_after_first = dashboard_recovered_minor(client, ANALYST_HEADERS)
    assert revenue_after_first - revenue_before == DEFAULT_AMOUNT_MINOR

    # Exact replay of the same provider event.
    assert post_webhook(client, success_payload, event_id=event_id).status_code == 204
    db_session.expire_all()
    assert db_session.get(RecoveryCase, case_id).status == RecoveryCaseStatus.RECOVERED.value
    assert count_outcomes(db_session, case_id) == 1
    outcome = db_session.execute(
        select(RecoveryOutcome).where(RecoveryOutcome.case_id == case_id)
    ).scalar_one()
    assert outcome.recovered_amount_minor == DEFAULT_AMOUNT_MINOR
    assert dashboard_recovered_minor(client, ANALYST_HEADERS) == revenue_after_first

    # A redelivery under a fresh event id must also not double count.
    assert post_webhook(client, success_payload, event_id=f"{event_id}_b").status_code == 204
    db_session.expire_all()
    assert count_outcomes(db_session, case_id) == 1
    assert dashboard_recovered_minor(client, ANALYST_HEADERS) == revenue_after_first

    assert timeline_event_types(client, case_id).count("CASE_RECOVERED") == 1


# ---------------------------------------------------------------------------
# Correlation, privacy, isolation
# ---------------------------------------------------------------------------


def test_success_event_cannot_resolve_an_uncorrelated_case(
    client, db_session, customer_external_id, provider_spy
) -> None:
    """A paid link for an unknown reference must not recover anything."""
    suffix = unique_suffix()
    case_id = open_case(
        client,
        db_session,
        payment_id=f"pay_uncorr_{suffix}",
        customer_external_id=customer_external_id,
        suffix=suffix,
    )
    drive_to_waiting_for_outcome(client, db_session, case_id)
    revenue_before = dashboard_recovered_minor(client, ANALYST_HEADERS)

    # Same tenant, same amount, but a reference belonging to no action.
    stray = post_webhook(
        client,
        payment_link_paid_payload(
            reference_id=f"rl_not_a_real_reference_{suffix}",
            payment_id=f"pay_uncorr_paid_{suffix}",
            amount_minor=DEFAULT_AMOUNT_MINOR,
        ),
        event_id=f"evt_uc_paid_{suffix}",
    )
    assert stray.status_code == 204

    db_session.expire_all()
    assert (
        db_session.get(RecoveryCase, case_id).status
        == RecoveryCaseStatus.WAITING_FOR_OUTCOME.value
    )
    assert count_outcomes(db_session, case_id) == 0
    assert dashboard_recovered_minor(client, ANALYST_HEADERS) == revenue_before


def test_success_with_mismatched_amount_does_not_recover(
    client, db_session, customer_external_id, provider_spy
) -> None:
    suffix = unique_suffix()
    case_id = open_case(
        client,
        db_session,
        payment_id=f"pay_money_{suffix}",
        customer_external_id=customer_external_id,
        suffix=suffix,
    )
    action = drive_to_waiting_for_outcome(client, db_session, case_id)
    revenue_before = dashboard_recovered_minor(client, ANALYST_HEADERS)

    assert (
        post_webhook(
            client,
            payment_link_paid_payload(
                reference_id=action.provider_reference,
                payment_id=f"pay_money_paid_{suffix}",
                amount_minor=DEFAULT_AMOUNT_MINOR + 1,
            ),
            event_id=f"evt_mm_paid_{suffix}",
        ).status_code
        == 204
    )

    db_session.expire_all()
    assert (
        db_session.get(RecoveryCase, case_id).status
        == RecoveryCaseStatus.WAITING_FOR_OUTCOME.value
    )
    assert count_outcomes(db_session, case_id) == 0
    assert dashboard_recovered_minor(client, ANALYST_HEADERS) == revenue_before


def test_timeline_never_exposes_raw_webhook_input(
    client, db_session, customer_external_id
) -> None:
    """Prompt 22 allowlisting still holds for events produced by the real flow."""
    suffix = unique_suffix()
    payment_id = f"pay_sentinel_{suffix}"
    assert (
        post_webhook(
            client,
            failure_payload(
                payment_id=payment_id,
                customer_external_id=customer_external_id,
                with_sentinel=True,
            ),
            event_id=f"evt_sentinel_{suffix}",
        ).status_code
        == 204
    )
    case_id = load_case(db_session, payment_id).id

    client.post(
        f"/api/v1/recovery-cases/{case_id}/analyze",
        headers=ANALYST_HEADERS,
        json={"reason": "MANUAL_ANALYSIS"},
    )

    response = client.get(
        f"/api/v1/recovery-cases/{case_id}/timeline", headers=ANALYST_HEADERS
    )
    assert response.status_code == 200
    raw = response.text
    assert SENSITIVE_SENTINEL not in raw
    assert "+919000000000" not in raw
    for forbidden in ("authorization", "signature", "secret", "@example.com"):
        assert forbidden not in raw.lower(), forbidden

    # Evidence is still present, just projected through the allowlist.
    items = response.json()["items"]
    assert items[0]["event_type"] == "CASE_CREATED"
    assert items[0]["evidence"]["payment_id"] == payment_id


def test_other_tenant_cannot_read_the_case_or_see_its_revenue(
    client, db_session, customer_external_id, provider_spy
) -> None:
    suffix = unique_suffix()
    case_id = open_case(
        client,
        db_session,
        payment_id=f"pay_tenant_{suffix}",
        customer_external_id=customer_external_id,
        suffix=suffix,
    )
    drive_to_waiting_for_outcome(client, db_session, case_id)

    foreign_org = uuid.uuid4()

    async def override_current_user() -> AuthContext:
        return AuthContext(
            user_id=uuid.uuid4(),
            organization_id=foreign_org,
            role=UserRole.ADMIN,
        )

    client.app.dependency_overrides[get_current_user] = override_current_user
    try:
        # The accepted contract denies a known case from another tenant with an
        # explicit 403 rather than a generic 404.
        detail = client.get(f"/api/v1/recovery-cases/{case_id}", headers=ANALYST_HEADERS)
        assert detail.status_code == 403
        assert detail.json()["error"]["code"] == "TENANT_ACCESS_DENIED"

        timeline = client.get(
            f"/api/v1/recovery-cases/{case_id}/timeline", headers=ANALYST_HEADERS
        )
        assert timeline.status_code == 403
        assert timeline.json()["error"]["code"] == "TENANT_ACCESS_DENIED"

        # Analytics are scoped to the authenticated tenant.
        assert dashboard_recovered_minor(client, ANALYST_HEADERS) == 0
    finally:
        client.app.dependency_overrides.pop(get_current_user, None)

    db_session.expire_all()
    assert (
        db_session.get(RecoveryCase, case_id).status
        == RecoveryCaseStatus.WAITING_FOR_OUTCOME.value
    )


# ---------------------------------------------------------------------------
# LLM-disabled and Prompt 23 separation
# ---------------------------------------------------------------------------


def test_recovery_workflow_operates_with_the_llm_disabled(
    client, db_session, customer_external_id, provider_spy, integration_settings, monkeypatch
) -> None:
    """The deterministic engine must own eligibility and money on its own."""
    from app.ai.factory import create_llm_provider, gemini_api_key_configured

    assert gemini_api_key_configured(integration_settings) is False
    assert create_llm_provider(integration_settings) is None

    llm_calls: list[str] = []

    class ForbiddenLLM:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            llm_calls.append("constructed")
            raise AssertionError("LLM must not be constructed while disabled.")

    monkeypatch.setattr("app.ai.factory.GeminiLLMProvider", ForbiddenLLM)

    suffix = unique_suffix()
    case_id = open_case(
        client,
        db_session,
        payment_id=f"pay_nollm_{suffix}",
        customer_external_id=customer_external_id,
        suffix=suffix,
    )

    analyze = client.post(
        f"/api/v1/recovery-cases/{case_id}/analyze",
        headers=ANALYST_HEADERS,
        json={"reason": "MANUAL_ANALYSIS"},
    )
    assert analyze.status_code == 200
    analysis = analyze.json()
    assert analysis["explanation_source"] == "TEMPLATE_FALLBACK"
    assert analysis["selected"] is not None
    assert analysis["selected"]["expected_recovered_minor"] >= 0

    create = client.post(
        f"/api/v1/recovery-cases/{case_id}/actions",
        headers=OPERATOR_HEADERS,
        json={
            "analysis_run_id": analysis["analysis_run_id"],
            "action_type": analysis["selected"]["action_type"],
        },
    )
    assert create.status_code == 201

    db_session.expire_all()
    approve = client.post(
        f"/api/v1/recovery-actions/{create.json()['action']['id']}/approve",
        headers=ADMIN_HEADERS,
        json={"expected_case_version": db_session.get(RecoveryCase, case_id).version},
    )
    assert approve.status_code == 200
    action = case_actions(db_session, case_id)[0]

    assert (
        post_webhook(
            client,
            payment_link_paid_payload(
                reference_id=action.provider_reference,
                payment_id=f"pay_nollm_paid_{suffix}",
                amount_minor=DEFAULT_AMOUNT_MINOR,
            ),
            event_id=f"evt_nollm_paid_{suffix}",
        ).status_code
        == 204
    )

    db_session.expire_all()
    assert db_session.get(RecoveryCase, case_id).status == RecoveryCaseStatus.RECOVERED.value
    assert count_outcomes(db_session, case_id) == 1
    assert llm_calls == []


def test_synthetic_demo_batch_does_not_touch_business_data_or_dashboard(
    client, db_session
) -> None:
    """Prompt 23 evaluation stays read-only and out of business analytics."""

    def business_counts() -> tuple[int, int, int]:
        return (
            int(db_session.execute(select(func.count()).select_from(RecoveryCase)).scalar_one()),
            int(
                db_session.execute(select(func.count()).select_from(RecoveryAction)).scalar_one()
            ),
            int(
                db_session.execute(select(func.count()).select_from(RecoveryOutcome)).scalar_one()
            ),
        )

    revenue_before = dashboard_recovered_minor(client, ANALYST_HEADERS)
    counts_before = business_counts()

    batch = client.post("/api/v1/demo/run-batch", headers=ADMIN_HEADERS)
    assert batch.status_code == 200, batch.text
    body = batch.json()
    assert body["data_source"] == "SYNTHETIC_SIMULATION"

    db_session.expire_all()
    assert business_counts() == counts_before
    assert dashboard_recovered_minor(client, ANALYST_HEADERS) == revenue_before

    # Synthetic output is vocabulary-separated from business revenue and is never
    # labelled as provider evidence.
    assert "revenue_recovered_minor" not in body
    assert "realized_synthetic_recovered_minor" in body["revloop_model_policy"]
    dashboard_text = client.get("/api/v1/dashboard/summary", headers=ANALYST_HEADERS).text
    assert "realized_synthetic_recovered_minor" not in dashboard_text
    assert "SYNTHETIC_SIMULATION" not in dashboard_text
