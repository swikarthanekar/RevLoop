"""HTTP-level security regressions for the recovery case timeline endpoint.

These tests exercise the real FastAPI route against the PostgreSQL-backed test
database. The invariant under test is stronger than "React does not render it":

    NO UNSAFE SENTINEL VALUE MAY CROSS THE HTTP BOUNDARY.

Assertions therefore inspect the complete serialized response body, not only the
parsed ``evidence`` mapping, so an unsafe value cannot hide in another field.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest

from app.demo.constants import DEMO_CASE_UPI_DOWNTIME_ID, DEMO_ORGANIZATION_ID
from app.domain.enums import AuditActorType
from app.models.audit_log import AuditLog
from tests.api.conftest import DEMO_AUTH_HEADERS

CASE_ID = DEMO_CASE_UPI_DOWNTIME_ID

SAFE_ANALYSIS_RUN_ID = "55555555-5555-4555-8555-555555555555"
SAFE_WEBHOOK_EVENT_ID = "66666666-6666-4666-8666-666666666666"
SAFE_ACTION_ID = "77777777-7777-4777-8777-777777777777"

# Legitimate evidence produced by real backend writers, which must survive.
SAFE_EVIDENCE: dict[str, object] = {
    "transition_event": "APPROVED_NOW",
    "previous_status": "AWAITING_APPROVAL",
    "new_status": "EXECUTING",
    "case_status": "EXECUTING",
    "previous_version": 4,
    "new_version": 5,
    "analysis_run_id": SAFE_ANALYSIS_RUN_ID,
    "action_id": SAFE_ACTION_ID,
    "webhook_event_id": SAFE_WEBHOOK_EVENT_ID,
    "scheduled_for": "2026-08-30T09:00:00+00:00",
    "rejection_recorded": True,
    "reason": "STALE_WEBHOOK_IGNORED",
    "source_event_key": "payment.failed:pay_123",
    "payment_id": "pay_SAFE123",
    "provider_event_id": "evt_SAFE123",
    "failure_category": "PAYMENT_RAIL_DOWNTIME",
    "selected_action": "CREATE_PAYMENT_LINK",
    "outcome": "RECOVERED",
    "policy_reasons": ["AMOUNT_ABOVE_AUTO_ACTION_LIMIT", "HIGH_VALUE_CUSTOMER"],
    "source": "SYNTHETIC_DEMO",
}

# Unsafe evidence a producer might have written historically. None of these
# key names or values may appear in the response.
UNSAFE_EVIDENCE: dict[str, object] = {
    "customer_email_address": "victim@example.com",
    "email": "victim@example.com",
    "phone": "+919876543210",
    "mobile": "+919876543210",
    "card_number": "4111111111111111",
    "signature": "whsec_SUPER_SECRET_SIGNATURE",
    "authorization": "Bearer VERY_SECRET_TOKEN",
    "token": "VERY_SECRET_TOKEN",
    "password": "super-secret-password",
    "secret": "provider-super-secret",
    "api_key": "sk_test_super_secret",
    "raw_payload": {"email": "victim@example.com"},
    "raw_response": "provider raw response secret-value",
    "webhook_body": "raw webhook body",
    "chain_of_thought": "private hidden reasoning",
    "reasoning": "private model reasoning",
    "prompt": "system/private prompt",
    "completion": "raw LLM completion",
    "database_url": "postgresql://user:password@host/db",
    "traceback": "Traceback (most recent call last): psycopg2.Error",
    "nested": {
        "authorization": "Bearer hidden",
        "email": "nested@example.com",
    },
}

# Every value fragment that must be absent from the serialized response body.
FORBIDDEN_FRAGMENTS: tuple[str, ...] = (
    "victim@example.com",
    "+919876543210",
    "4111111111111111",
    "whsec_SUPER_SECRET_SIGNATURE",
    "VERY_SECRET_TOKEN",
    "super-secret-password",
    "provider-super-secret",
    "sk_test_super_secret",
    "private hidden reasoning",
    "private model reasoning",
    "system/private prompt",
    "raw LLM completion",
    "postgresql://",
    "psycopg2.Error",
    "nested@example.com",
    "provider raw response secret-value",
    "raw webhook body",
    "Bearer hidden",
)


def _insert_audit(db_session, *, event_type: str, evidence: dict[str, object]) -> uuid.UUID:
    entry = AuditLog(
        id=uuid.uuid4(),
        organization_id=DEMO_ORGANIZATION_ID,
        case_id=CASE_ID,
        actor_type=AuditActorType.SYSTEM.value,
        actor_id="security-regression",
        event_type=event_type,
        summary="Security regression fixture event.",
        evidence=evidence,
    )
    db_session.add(entry)
    db_session.commit()
    return entry.id


@pytest.fixture
def audit_row(db_session) -> Iterator[callable]:
    """Insert audit rows and remove them afterwards, keeping the suite order-independent."""
    created: list[uuid.UUID] = []

    def _create(*, event_type: str, evidence: dict[str, object]) -> uuid.UUID:
        entry_id = _insert_audit(db_session, event_type=event_type, evidence=evidence)
        created.append(entry_id)
        return entry_id

    try:
        yield _create
    finally:
        for entry_id in created:
            row = db_session.get(AuditLog, entry_id)
            if row is not None:
                db_session.delete(row)
        db_session.commit()


def _fetch_timeline(api_client):
    response = api_client.get(
        f"/api/v1/recovery-cases/{CASE_ID}/timeline",
        headers=DEMO_AUTH_HEADERS,
    )
    assert response.status_code == 200
    return response


def _entry_for(response, event_type: str) -> dict:
    return next(
        item for item in response.json()["items"] if item["event_type"] == event_type
    )


def test_unsafe_evidence_never_crosses_the_http_boundary(api_client, audit_row) -> None:
    """Safe fields survive; every unsafe sentinel is absent from the whole body."""
    audit_row(
        event_type="SECURITY_MIXED_EVIDENCE",
        evidence={**SAFE_EVIDENCE, **UNSAFE_EVIDENCE},
    )

    response = _fetch_timeline(api_client)
    body = response.text
    evidence = _entry_for(response, "SECURITY_MIXED_EVIDENCE")["evidence"]

    # 1. Legitimate operator-facing evidence is preserved.
    for key, expected in SAFE_EVIDENCE.items():
        assert evidence[key] == expected, f"safe key {key!r} was dropped"

    # 2. No unsafe key name is present.
    for key in UNSAFE_EVIDENCE:
        assert key not in evidence, f"unsafe key {key!r} crossed the boundary"

    # 3. The projection is exactly the allowlisted safe set — nothing extra.
    assert set(evidence) == set(SAFE_EVIDENCE)

    # 4. No unsafe value appears anywhere in the complete serialized response.
    for fragment in FORBIDDEN_FRAGMENTS:
        assert fragment not in body, f"sentinel {fragment!r} leaked into the response body"


def test_malicious_value_under_allowlisted_key_is_omitted(api_client, audit_row) -> None:
    """A safe key name with an unsafe value must still fail closed."""
    audit_row(
        event_type="SECURITY_MALICIOUS_VALUE",
        evidence={
            "payment_id": "Traceback (most recent call last): psycopg2.Error password=secret",
            "provider_event_id": {"nested": "unexpected-object"},
            "previous_version": {"nested": "unexpected-object"},
            "policy_reasons": [{"authorization": "Bearer hidden"}],
            "source": "SYNTHETIC_DEMO",
        },
    )

    response = _fetch_timeline(api_client)
    body = response.text
    evidence = _entry_for(response, "SECURITY_MALICIOUS_VALUE")["evidence"]

    # Only the one valid field survives.
    assert evidence == {"source": "SYNTHETIC_DEMO"}
    for key in ("payment_id", "provider_event_id", "previous_version", "policy_reasons"):
        assert key not in evidence

    # No coercion artefact of any kind was produced.
    for artefact in (
        "psycopg2.Error",
        "password=secret",
        "Traceback",
        "unexpected-object",
        "Bearer hidden",
        "[object Object]",
        "{'nested'",
    ):
        assert artefact not in body


def test_unknown_future_key_is_omitted(api_client, audit_row) -> None:
    """A future producer does not automatically become a public API field."""
    audit_row(
        event_type="SECURITY_UNKNOWN_KEY",
        evidence={
            "totally_new_future_field": "harmless-looking-but-unreviewed-value",
            "source": "SYNTHETIC_DEMO",
        },
    )

    response = _fetch_timeline(api_client)
    evidence = _entry_for(response, "SECURITY_UNKNOWN_KEY")["evidence"]

    assert evidence == {"source": "SYNTHETIC_DEMO"}
    assert "totally_new_future_field" not in evidence
    assert "harmless-looking-but-unreviewed-value" not in response.text


def test_operator_authored_rejection_reason_is_not_published(api_client, audit_row) -> None:
    """`reason` also carries operator free text, which must not be republished.

    System reasons are SCREAMING_SNAKE constants; the operator rejection text
    written by the actions service is arbitrary prose and fails the validator.
    """
    audit_row(
        event_type="SECURITY_OPERATOR_REASON",
        evidence={
            "reason": "APPROVAL_REJECTED:call the customer on +919876543210",
            "transition_event": "APPROVAL_REJECTED_STOP",
        },
    )

    response = _fetch_timeline(api_client)
    evidence = _entry_for(response, "SECURITY_OPERATOR_REASON")["evidence"]

    assert "reason" not in evidence
    assert evidence == {"transition_event": "APPROVAL_REJECTED_STOP"}
    assert "+919876543210" not in response.text


def test_timeline_ordering_is_unchanged(api_client, audit_row) -> None:
    """Canonical ordering (created_at ASC, id ASC) is preserved by the hardening."""
    audit_row(event_type="SECURITY_ORDERING", evidence={"source": "SYNTHETIC_DEMO"})

    response = _fetch_timeline(api_client)
    items = response.json()["items"]

    timestamps = [item["occurred_at"] for item in items]
    assert timestamps == sorted(timestamps)
    # Ties are broken by id, so the full (created_at, id) key is non-decreasing.
    keys = [(item["occurred_at"], item["id"]) for item in items]
    assert keys == sorted(keys)
    assert items[0]["event_type"] == "CASE_CREATED"


def test_summary_is_backend_generated_and_safe(api_client) -> None:
    """Seeded summaries are backend-authored operator text, free of payloads."""
    response = _fetch_timeline(api_client)
    summaries = [item["summary"] for item in response.json()["items"]]

    assert summaries and all(summary.strip() for summary in summaries)
    for summary in summaries:
        assert len(summary) <= 500
        assert "{" not in summary and "}" not in summary
        assert "@" not in summary
        assert "Traceback" not in summary
        assert "Bearer" not in summary
