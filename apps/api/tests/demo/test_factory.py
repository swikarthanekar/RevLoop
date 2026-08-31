"""Pure deterministic demo factory tests."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal

from app.demo.constants import (
    CUSTOMER_COUNT,
    DEMO_CASE_HIGH_VALUE_APPROVAL_ID,
    DEMO_CASE_RECOVERED_HISTORY_ID,
    DEMO_CASE_UPI_DOWNTIME_ID,
    DEMO_ORGANIZATION_ID,
    DEMO_SEED_VERSION,
    RECOVERY_CASE_COUNT,
    TRANSACTION_COUNT,
    demo_uuid,
)
from app.demo.factory import (
    DEMO_ERROR_REASON_TO_FAILURE_CATEGORY,
    TERMINAL_STATUSES,
    build_demo_seed_spec,
    demo_failure_category_from_transaction,
    demo_source_event_key,
)
from app.demo.summary import build_spec_summary
from app.domain.enums import RecoveryCaseStatus


def test_demo_uuid_is_deterministic() -> None:
    first = demo_uuid("customer:0001")
    second = demo_uuid("customer:0001")
    assert first == second
    assert str(first) != str(demo_uuid("customer:0002"))


def test_build_demo_seed_spec_counts() -> None:
    spec = build_demo_seed_spec()
    assert spec.organization.id == DEMO_ORGANIZATION_ID
    assert len(spec.customers) == CUSTOMER_COUNT
    assert len(spec.transactions) == TRANSACTION_COUNT
    assert len(spec.subscriptions) == 32
    assert len(spec.recovery_cases) == RECOVERY_CASE_COUNT
    assert spec.merchant_policy is not None


def test_named_case_ids_are_stable() -> None:
    spec = build_demo_seed_spec()
    by_id = {case.id: case for case in spec.recovery_cases}
    assert by_id[DEMO_CASE_UPI_DOWNTIME_ID].status == RecoveryCaseStatus.RECOMMENDED.value
    assert by_id[DEMO_CASE_HIGH_VALUE_APPROVAL_ID].status == (
        RecoveryCaseStatus.AWAITING_APPROVAL.value
    )
    assert by_id[DEMO_CASE_RECOVERED_HISTORY_ID].status == RecoveryCaseStatus.RECOVERED.value


def test_money_fields_use_integer_minor_units() -> None:
    spec = build_demo_seed_spec()
    for txn in spec.transactions:
        assert isinstance(txn.amount_minor, int)
        assert txn.amount_minor > 0
    for case in spec.recovery_cases:
        assert case.amount_at_risk_minor > 0


def test_all_synthetic_flags_true() -> None:
    spec = build_demo_seed_spec()
    assert all(customer.is_synthetic for customer in spec.customers)
    assert all(txn.is_synthetic for txn in spec.transactions)
    assert all(sub.is_synthetic for sub in spec.subscriptions)


def test_case_type_distribution() -> None:
    spec = build_demo_seed_spec()
    counts = Counter(case.case_type for case in spec.recovery_cases)
    assert counts["PAYMENT_FAILURE"] == 75
    assert counts["SUBSCRIPTION_FAILURE"] == 25


def test_case_state_distribution() -> None:
    spec = build_demo_seed_spec()
    counts = Counter(case.status for case in spec.recovery_cases)
    assert counts[RecoveryCaseStatus.DETECTED.value] == 8
    assert counts[RecoveryCaseStatus.RECOMMENDED.value] == 15
    assert counts[RecoveryCaseStatus.RECOVERED.value] == 38


def test_terminal_cases_have_outcomes_and_resolved_at() -> None:
    spec = build_demo_seed_spec()
    terminal_cases = [case for case in spec.recovery_cases if case.status in TERMINAL_STATUSES]
    outcome_by_case = {outcome.case_id: outcome for outcome in spec.outcomes}
    assert len(terminal_cases) == len(spec.outcomes)
    for case in terminal_cases:
        assert case.resolved_at is not None
        outcome = outcome_by_case[case.id]
        if case.status == RecoveryCaseStatus.RECOVERED.value:
            assert outcome.outcome == "RECOVERED"
            assert outcome.recovered_amount_minor > 0
        elif case.status == RecoveryCaseStatus.FAILED.value:
            assert outcome.outcome == "NOT_RECOVERED"
            assert outcome.recovered_amount_minor == 0
        else:
            assert outcome.outcome == "STOPPED"
            assert outcome.recovered_amount_minor == 0


def test_nonterminal_cases_have_no_outcome() -> None:
    spec = build_demo_seed_spec()
    outcome_cases = {outcome.case_id for outcome in spec.outcomes}
    for case in spec.recovery_cases:
        if case.status not in TERMINAL_STATUSES:
            assert case.resolved_at is None
            assert case.id not in outcome_cases


def test_recommendation_json_shapes() -> None:
    spec = build_demo_seed_spec()
    assert spec.recommendations
    for rec in spec.recommendations:
        assert isinstance(rec.policy_reasons, list)
        assert isinstance(rec.factors, list)
        for factor in rec.factors:
            assert set(factor.keys()).issubset({"code", "impact", "source"})
            assert all(isinstance(value, str) for value in factor.values())


def test_idempotency_keys_are_unique() -> None:
    spec = build_demo_seed_spec()
    keys = [action.idempotency_key for action in spec.actions]
    assert len(keys) == len(set(keys))


def test_recovered_history_has_rich_audit_timeline() -> None:
    spec = build_demo_seed_spec()
    logs = [log for log in spec.audit_logs if log.case_id == DEMO_CASE_RECOVERED_HISTORY_ID]
    assert len(logs) >= 6
    timestamps = [log.created_at for log in logs]
    assert timestamps == sorted(timestamps)


def test_spec_summary_is_deterministic() -> None:
    first = build_spec_summary()
    second = build_spec_summary()
    assert first == second
    assert first.seed_version == DEMO_SEED_VERSION
    assert first.customers == CUSTOMER_COUNT
    assert 80 <= first.recovery_cases <= 120


def test_flagship_upi_case_properties() -> None:
    spec = build_demo_seed_spec()
    case = next(case for case in spec.recovery_cases if case.id == DEMO_CASE_UPI_DOWNTIME_ID)
    assert case.amount_at_risk_minor == 499900
    assert case.failure_category == "PAYMENT_RAIL_DOWNTIME"
    recs = [rec for rec in spec.recommendations if rec.case_id == case.id]
    rank1 = next(rec for rec in recs if rec.rank == 1)
    assert rank1.action_type == "REQUEST_ALTERNATE_PAYMENT_METHOD"
    assert rank1.success_probability == Decimal("0.82")


def test_high_value_case_requires_approval() -> None:
    spec = build_demo_seed_spec()
    case = next(
        case for case in spec.recovery_cases if case.id == DEMO_CASE_HIGH_VALUE_APPROVAL_ID
    )
    assert case.amount_at_risk_minor == 3500000
    recs = [rec for rec in spec.recommendations if rec.case_id == case.id]
    assert any(rec.requires_approval for rec in recs)
    assert any("AMOUNT_ABOVE_AUTO_ACTION_LIMIT" in rec.policy_reasons for rec in recs)


def test_payment_cases_use_unique_source_transactions() -> None:
    spec = build_demo_seed_spec()
    payment_cases = [
        case for case in spec.recovery_cases if case.case_type == "PAYMENT_FAILURE"
    ]
    payment_ids = [case.transaction_id for case in payment_cases]
    assert len(payment_cases) == 75
    assert len(set(payment_ids)) == 75


def test_subscription_cases_use_unique_source_subscriptions() -> None:
    spec = build_demo_seed_spec()
    subscription_cases = [
        case for case in spec.recovery_cases if case.case_type == "SUBSCRIPTION_FAILURE"
    ]
    subscription_ids = [case.subscription_id for case in subscription_cases]
    assert len(subscription_cases) == 25
    assert len(set(subscription_ids)) == 25


def test_source_event_keys_are_unique_and_source_derived() -> None:
    spec = build_demo_seed_spec()
    keys = [case.source_event_key for case in spec.recovery_cases]
    assert len(keys) == 100
    assert len(set(keys)) == 100

    for case in spec.recovery_cases:
        expected = demo_source_event_key(case.case_type, case.transaction_id, case.subscription_id)
        assert case.source_event_key == expected


def test_all_payment_cases_align_failure_category_with_transaction_evidence() -> None:
    spec = build_demo_seed_spec()
    transactions_by_id = {txn.id: txn for txn in spec.transactions}
    payment_cases = [
        case for case in spec.recovery_cases if case.case_type == "PAYMENT_FAILURE"
    ]

    mismatches = []
    for case in payment_cases:
        txn = transactions_by_id[case.transaction_id]
        expected = demo_failure_category_from_transaction(txn)
        if case.failure_category != expected:
            mismatches.append((case.id, case.failure_category, expected, txn.error_reason))

    assert mismatches == []


def test_subscription_failure_metadata_present_where_expected() -> None:
    spec = build_demo_seed_spec()
    recovered_subscription = next(
        sub for sub in spec.subscriptions if sub.metadata.get("recovered") is True
    )
    assert recovered_subscription.metadata["previous_failure_reason"] == "mandate_failure"
    assert (
        recovered_subscription.metadata["previous_failure_category"]
        == "MANDATE_OR_RECURRING_FAILURE"
    )

    pending_or_halted = [
        sub
        for sub in spec.subscriptions
        if sub.status in {"PENDING", "HALTED"}
    ]
    assert pending_or_halted
    for sub in pending_or_halted:
        assert "last_failure_reason" in sub.metadata
        assert "last_failure_category" in sub.metadata
        assert sub.metadata["last_failure_category"] == DEMO_ERROR_REASON_TO_FAILURE_CATEGORY.get(
            sub.metadata["last_failure_reason"],
            "UNKNOWN",
        )


def test_named_upi_case_transaction_evidence_matches_category() -> None:
    spec = build_demo_seed_spec()
    case = next(case for case in spec.recovery_cases if case.id == DEMO_CASE_UPI_DOWNTIME_ID)
    txn = next(txn for txn in spec.transactions if txn.id == case.transaction_id)
    assert txn.error_reason == "payment_rail_unavailable"
    assert txn.payment_method == "UPI"
    assert case.failure_category == "PAYMENT_RAIL_DOWNTIME"


def test_named_high_value_case_transaction_evidence_matches_category() -> None:
    spec = build_demo_seed_spec()
    case = next(
        case for case in spec.recovery_cases if case.id == DEMO_CASE_HIGH_VALUE_APPROVAL_ID
    )
    txn = next(txn for txn in spec.transactions if txn.id == case.transaction_id)
    assert txn.error_reason == "insufficient_funds"
    assert case.failure_category == "INSUFFICIENT_FUNDS"


def test_named_recovered_history_subscription_preserves_previous_failure_context() -> None:
    spec = build_demo_seed_spec()
    case = next(
        case for case in spec.recovery_cases if case.id == DEMO_CASE_RECOVERED_HISTORY_ID
    )
    sub = next(sub for sub in spec.subscriptions if sub.id == case.subscription_id)
    assert case.case_type == "SUBSCRIPTION_FAILURE"
    assert case.failure_category == "MANDATE_OR_RECURRING_FAILURE"
    assert sub.metadata["previous_failure_reason"] == "mandate_failure"
    assert sub.status == "ACTIVE"
