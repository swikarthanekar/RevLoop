"""Unit tests for the fail-closed public timeline evidence projection.

The HTTP regression in ``tests/api/test_timeline_security.py`` is the primary
acceptance test. These focus on the projection rules themselves.
"""

from __future__ import annotations

import copy

import pytest

from app.services.timeline_evidence import (
    project_timeline_evidence,
    public_evidence_keys,
)

VALID_UUID = "55555555-5555-4555-8555-555555555555"


class TestKnownKeysAreRetained:
    @pytest.mark.parametrize(
        ("key", "value"),
        [
            ("transition_event", "APPROVED_NOW"),
            ("previous_status", "AWAITING_APPROVAL"),
            ("new_status", "EXECUTING"),
            ("case_status", "RECOVERED"),
            ("previous_version", 4),
            ("new_version", 5),
            ("analysis_run_id", VALID_UUID),
            ("action_id", VALID_UUID),
            ("webhook_event_id", VALID_UUID),
            ("scheduled_for", "2026-08-30T09:00:00+00:00"),
            ("rejection_recorded", True),
            ("reason", "STALE_WEBHOOK_IGNORED"),
            ("source_event_key", "payment.failed:pay_123"),
            ("payment_id", "pay_SAFE123"),
            ("provider_event_id", "evt_SAFE123"),
            ("failure_category", "PAYMENT_RAIL_DOWNTIME"),
            ("selected_action", "CREATE_PAYMENT_LINK"),
            ("outcome", "RECOVERED"),
            ("source", "SYNTHETIC_DEMO"),
        ],
    )
    def test_valid_value_survives(self, key: str, value: object) -> None:
        assert project_timeline_evidence({key: value}) == {key: value}

    def test_valid_list_survives(self) -> None:
        evidence = {"policy_reasons": ["AMOUNT_ABOVE_AUTO_ACTION_LIMIT", "HIGH_VALUE"]}
        assert project_timeline_evidence(evidence) == evidence

    def test_zero_and_false_are_not_dropped(self) -> None:
        # Falsy-but-valid values must survive; the projection tests validity,
        # not truthiness.
        result = project_timeline_evidence(
            {"previous_version": 0, "rejection_recorded": False}
        )
        assert result == {"previous_version": 0, "rejection_recorded": False}


class TestUnknownKeys:
    def test_unknown_key_is_omitted(self) -> None:
        assert project_timeline_evidence(
            {"totally_new_future_field": "harmless-looking-but-unreviewed-value"}
        ) == {}

    @pytest.mark.parametrize(
        "key",
        [
            "authorization",
            "api_key",
            "secret",
            "password",
            "token",
            "webhook_secret",
            "signature",
            "email",
            "customer_email_address",
            "phone",
            "mobile",
            "card_number",
            "raw_payload",
            "raw_response",
            "webhook_body",
            "chain_of_thought",
            "reasoning",
            "prompt",
            "completion",
            "database_url",
            "traceback",
            "stack_trace",
            "metadata",
            "approver_id",
        ],
    )
    def test_sensitive_key_is_omitted(self, key: str) -> None:
        assert project_timeline_evidence({key: "anything at all"}) == {}

    def test_allowlist_is_the_only_source_of_keys(self) -> None:
        noisy = {f"unreviewed_key_{index}": "value" for index in range(50)}
        assert project_timeline_evidence(noisy) == {}


class TestInvalidValuesFailClosed:
    def test_wrong_type_is_omitted(self) -> None:
        assert project_timeline_evidence({"previous_version": "4"}) == {}
        assert project_timeline_evidence({"rejection_recorded": "true"}) == {}
        assert project_timeline_evidence({"source": 123}) == {}

    def test_nested_object_under_primitive_key_is_omitted(self) -> None:
        assert project_timeline_evidence(
            {"provider_event_id": {"nested": "unexpected-object"}}
        ) == {}
        assert project_timeline_evidence({"source": {"a": "b"}}) == {}

    def test_arbitrary_prose_under_identifier_key_is_omitted(self) -> None:
        assert project_timeline_evidence(
            {"payment_id": "Traceback (most recent call last): psycopg2.Error password=secret"}
        ) == {}

    def test_control_characters_are_omitted(self) -> None:
        assert project_timeline_evidence(
            {"payment_id": "pay_1\nAuthorization: Bearer leak"}
        ) == {}
        assert project_timeline_evidence({"source": "SAFE\x00VALUE"}) == {}

    def test_oversized_string_is_omitted(self) -> None:
        assert project_timeline_evidence({"payment_id": "x" * 500}) == {}
        assert project_timeline_evidence({"source": "A" * 500}) == {}

    def test_bool_is_not_accepted_as_integer(self) -> None:
        # bool subclasses int in Python; True must not be published as 1.
        assert project_timeline_evidence({"previous_version": True}) == {}
        assert project_timeline_evidence({"new_version": False}) == {}

    def test_float_is_not_accepted_where_integer_required(self) -> None:
        assert project_timeline_evidence({"new_version": 5.0}) == {}

    def test_out_of_range_integer_is_omitted(self) -> None:
        assert project_timeline_evidence({"new_version": -1}) == {}
        assert project_timeline_evidence({"new_version": 10**9}) == {}

    def test_non_enum_value_is_omitted(self) -> None:
        # Enum-backed keys validate against the real backend value set.
        assert project_timeline_evidence({"new_status": "NOT_A_REAL_STATUS"}) == {}
        assert project_timeline_evidence({"failure_category": "MADE_UP"}) == {}
        assert project_timeline_evidence({"selected_action": "DROP TABLE"}) == {}

    def test_invalid_uuid_is_omitted(self) -> None:
        assert project_timeline_evidence({"analysis_run_id": "not-a-uuid"}) == {}

    def test_invalid_timestamp_is_omitted(self) -> None:
        assert project_timeline_evidence({"scheduled_for": "whenever"}) == {}

    def test_operator_prose_reason_is_omitted(self) -> None:
        assert project_timeline_evidence({"reason": "Operator selected STOP."}) == {}
        assert project_timeline_evidence(
            {"reason": "APPROVAL_REJECTED:call +919876543210"}
        ) == {}

    def test_system_reason_token_is_retained(self) -> None:
        assert project_timeline_evidence({"reason": "RECOVERY_MONEY_MISMATCH"}) == {
            "reason": "RECOVERY_MONEY_MISMATCH"
        }


class TestLists:
    def test_list_with_invalid_member_is_dropped_entirely(self) -> None:
        # A partially filtered list would misrepresent the audit record.
        assert project_timeline_evidence(
            {"policy_reasons": ["VALID_REASON", {"authorization": "Bearer hidden"}]}
        ) == {}

    def test_list_of_wrong_primitive_is_omitted(self) -> None:
        assert project_timeline_evidence({"policy_reasons": [1, 2, 3]}) == {}

    def test_oversized_list_is_omitted(self) -> None:
        assert project_timeline_evidence(
            {"policy_reasons": [f"REASON_{index}" for index in range(20)]}
        ) == {}

    def test_empty_list_is_omitted(self) -> None:
        assert project_timeline_evidence({"policy_reasons": []}) == {}

    def test_nested_list_is_omitted(self) -> None:
        assert project_timeline_evidence({"policy_reasons": [["NESTED"]]}) == {}


class TestProjectionHygiene:
    def test_input_is_not_mutated(self) -> None:
        evidence = {
            "source": "SYNTHETIC_DEMO",
            "authorization": "Bearer VERY_SECRET_TOKEN",
            "policy_reasons": ["SAFE_REASON"],
        }
        snapshot = copy.deepcopy(evidence)

        project_timeline_evidence(evidence)

        assert evidence == snapshot

    def test_returned_list_is_not_the_stored_list(self) -> None:
        stored = ["SAFE_REASON"]
        result = project_timeline_evidence({"policy_reasons": stored})
        result["policy_reasons"].append("MUTATED")

        assert stored == ["SAFE_REASON"]

    def test_empty_and_missing_evidence(self) -> None:
        assert project_timeline_evidence({}) == {}
        assert project_timeline_evidence(None) == {}

    def test_non_mapping_evidence(self) -> None:
        assert project_timeline_evidence("a string") == {}
        assert project_timeline_evidence([{"source": "SYNTHETIC_DEMO"}]) == {}

    def test_projection_is_a_subset_of_the_allowlist(self) -> None:
        mixed = {
            "source": "SYNTHETIC_DEMO",
            "authorization": "Bearer hidden",
            "unknown_key": "value",
        }
        assert set(project_timeline_evidence(mixed)) <= public_evidence_keys()

    def test_allowlist_excludes_deliberately_unpublished_keys(self) -> None:
        # `metadata` is a free-form nested mapping and `approver_id` identifies a
        # person; both are produced by the state machine but never published.
        keys = public_evidence_keys()
        assert "metadata" not in keys
        assert "approver_id" not in keys
