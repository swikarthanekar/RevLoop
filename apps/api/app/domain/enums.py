from enum import Enum


class RecoveryCaseStatus(str, Enum):
    DETECTED = "DETECTED"
    ANALYZING = "ANALYZING"
    RECOMMENDED = "RECOMMENDED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    SCHEDULED = "SCHEDULED"
    EXECUTING = "EXECUTING"
    WAITING_FOR_OUTCOME = "WAITING_FOR_OUTCOME"
    RECOVERED = "RECOVERED"
    FAILED = "FAILED"
    STOPPED = "STOPPED"


class CaseType(str, Enum):
    PAYMENT_FAILURE = "PAYMENT_FAILURE"
    SUBSCRIPTION_FAILURE = "SUBSCRIPTION_FAILURE"
    OVERDUE_INVOICE = "OVERDUE_INVOICE"


class RecoveryActionType(str, Enum):
    WAIT = "WAIT"
    RETRY_SAME_METHOD = "RETRY_SAME_METHOD"
    REQUEST_ALTERNATE_PAYMENT_METHOD = "REQUEST_ALTERNATE_PAYMENT_METHOD"
    CREATE_PAYMENT_LINK = "CREATE_PAYMENT_LINK"
    SEND_RECOVERY_MESSAGE = "SEND_RECOVERY_MESSAGE"
    ESCALATE_TO_HUMAN = "ESCALATE_TO_HUMAN"
    STOP = "STOP"


#: Candidate action types whose only implemented delivery mechanism in P0 is a
#: Razorpay Standard Payment Link. A Payment Link's checkout page lets the
#: customer choose whichever payment method is available, which is
#: mechanically what REQUEST_ALTERNATE_PAYMENT_METHOD asks for -- there is no
#: separate "alternate method" provider call. Every place that gates Payment
#: Link creation, approval, idempotent reconciliation, or the
#: `payment_link.paid` webhook lookup must treat every member of this set the
#: same way, keyed on the RecoveryAction's own (never rewritten) action_type.
PAYMENT_LINK_MECHANISM_ACTIONS = frozenset(
    {
        RecoveryActionType.CREATE_PAYMENT_LINK,
        RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD,
    }
)


class RecoveryActionStatus(str, Enum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    SCHEDULED = "SCHEDULED"
    EXECUTING = "EXECUTING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    CANCELLED = "CANCELLED"


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    OPERATOR = "OPERATOR"
    ANALYST = "ANALYST"


class FailureCategory(str, Enum):
    PAYMENT_RAIL_DOWNTIME = "PAYMENT_RAIL_DOWNTIME"
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    AUTHENTICATION_FAILURE = "AUTHENTICATION_FAILURE"
    BANK_OR_ISSUER_DECLINE = "BANK_OR_ISSUER_DECLINE"
    EXPIRED_OR_INVALID_METHOD = "EXPIRED_OR_INVALID_METHOD"
    CUSTOMER_ABANDONMENT = "CUSTOMER_ABANDONMENT"
    MANDATE_OR_RECURRING_FAILURE = "MANDATE_OR_RECURRING_FAILURE"
    TECHNICAL_FAILURE = "TECHNICAL_FAILURE"
    UNKNOWN = "UNKNOWN"


class RecoveryOutcomeType(str, Enum):
    RECOVERED = "RECOVERED"
    NOT_RECOVERED = "NOT_RECOVERED"
    STOPPED = "STOPPED"


class VerificationSource(str, Enum):
    WEBHOOK = "WEBHOOK"
    PROVIDER_FETCH = "PROVIDER_FETCH"
    SIMULATED_BATCH = "SIMULATED_BATCH"


class WebhookProcessingStatus(str, Enum):
    RECEIVED = "RECEIVED"
    PROCESSED = "PROCESSED"
    IGNORED = "IGNORED"
    FAILED = "FAILED"


class AuditActorType(str, Enum):
    SYSTEM = "SYSTEM"
    USER = "USER"
    PROVIDER = "PROVIDER"
    MODEL = "MODEL"


class AnalysisReason(str, Enum):
    MANUAL_ANALYSIS = "MANUAL_ANALYSIS"
    SCHEDULED_REEVALUATION = "SCHEDULED_REEVALUATION"
    NEW_PROVIDER_EVIDENCE = "NEW_PROVIDER_EVIDENCE"
