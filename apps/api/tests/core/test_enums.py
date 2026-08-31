from app.domain.enums import (
    AnalysisReason,
    AuditActorType,
    CaseType,
    FailureCategory,
    RecoveryActionStatus,
    RecoveryActionType,
    RecoveryCaseStatus,
    RecoveryOutcomeType,
    UserRole,
    VerificationSource,
    WebhookProcessingStatus,
)


def test_recovery_case_status_values_match_state_machine() -> None:
    expected = {
        "DETECTED",
        "ANALYZING",
        "RECOMMENDED",
        "AWAITING_APPROVAL",
        "SCHEDULED",
        "EXECUTING",
        "WAITING_FOR_OUTCOME",
        "RECOVERED",
        "FAILED",
        "STOPPED",
    }
    assert {member.value for member in RecoveryCaseStatus} == expected


def test_case_type_values_match_schema() -> None:
    expected = {"PAYMENT_FAILURE", "SUBSCRIPTION_FAILURE", "OVERDUE_INVOICE"}
    assert {member.value for member in CaseType} == expected


def test_recovery_action_type_values_match_schema() -> None:
    expected = {
        "WAIT",
        "RETRY_SAME_METHOD",
        "REQUEST_ALTERNATE_PAYMENT_METHOD",
        "CREATE_PAYMENT_LINK",
        "SEND_RECOVERY_MESSAGE",
        "ESCALATE_TO_HUMAN",
        "STOP",
    }
    assert {member.value for member in RecoveryActionType} == expected


def test_recovery_action_status_values_match_schema() -> None:
    expected = {
        "PENDING_APPROVAL",
        "SCHEDULED",
        "EXECUTING",
        "SUCCEEDED",
        "FAILED",
        "UNKNOWN",
        "CANCELLED",
    }
    assert {member.value for member in RecoveryActionStatus} == expected


def test_user_role_values_match_contract() -> None:
    expected = {"ADMIN", "OPERATOR", "ANALYST"}
    assert {member.value for member in UserRole} == expected


def test_failure_category_values_match_recovery_engine() -> None:
    expected = {
        "PAYMENT_RAIL_DOWNTIME",
        "INSUFFICIENT_FUNDS",
        "AUTHENTICATION_FAILURE",
        "BANK_OR_ISSUER_DECLINE",
        "EXPIRED_OR_INVALID_METHOD",
        "CUSTOMER_ABANDONMENT",
        "MANDATE_OR_RECURRING_FAILURE",
        "TECHNICAL_FAILURE",
        "UNKNOWN",
    }
    assert {member.value for member in FailureCategory} == expected


def test_recovery_outcome_type_values_match_domain_model() -> None:
    expected = {"RECOVERED", "NOT_RECOVERED", "STOPPED"}
    assert {member.value for member in RecoveryOutcomeType} == expected


def test_verification_source_values_match_domain_model() -> None:
    expected = {"WEBHOOK", "PROVIDER_FETCH", "SIMULATED_BATCH"}
    assert {member.value for member in VerificationSource} == expected


def test_webhook_processing_status_values_match_domain_model() -> None:
    expected = {"RECEIVED", "PROCESSED", "IGNORED", "FAILED"}
    assert {member.value for member in WebhookProcessingStatus} == expected


def test_audit_actor_type_values_match_domain_model() -> None:
    expected = {"SYSTEM", "USER", "PROVIDER", "MODEL"}
    assert {member.value for member in AuditActorType} == expected


def test_analysis_reason_values_match_api_contract() -> None:
    expected = {"MANUAL_ANALYSIS", "SCHEDULED_REEVALUATION", "NEW_PROVIDER_EVIDENCE"}
    assert {member.value for member in AnalysisReason} == expected
