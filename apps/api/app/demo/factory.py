"""Pure deterministic demo fixture generation (no database I/O)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.demo.constants import (
    ALLOWED_ACTION_TYPES,
    AUTO_ACTION_LIMIT_MINOR,
    CASE_STATE_COUNTS,
    COOLDOWN_MINUTES,
    CUSTOMER_COUNT,
    DEMO_ANALYSIS_HIGH_VALUE_ID,
    DEMO_ANALYSIS_RECOVERED_HISTORY_ID,
    DEMO_ANALYSIS_UPI_DOWNTIME_ID,
    DEMO_AUTH_USER_ADMIN_ID,
    DEMO_AUTH_USER_ANALYST_ID,
    DEMO_AUTH_USER_OPERATOR_ID,
    DEMO_CASE_HIGH_VALUE_APPROVAL,
    DEMO_CASE_HIGH_VALUE_APPROVAL_ID,
    DEMO_CASE_RECOVERED_HISTORY,
    DEMO_CASE_RECOVERED_HISTORY_ID,
    DEMO_CASE_UPI_DOWNTIME,
    DEMO_CASE_UPI_DOWNTIME_ID,
    DEMO_MERCHANT_POLICY_ID,
    DEMO_ORGANIZATION_CURRENCY,
    DEMO_ORGANIZATION_ID,
    DEMO_ORGANIZATION_NAME,
    DEMO_USER_ADMIN_ID,
    DEMO_USER_ANALYST_ID,
    DEMO_USER_OPERATOR_ID,
    FIRST_NAMES,
    INVOICE_COUNT,
    LAST_NAMES,
    MAX_CONTACTS_PER_24H,
    MAX_RECOVERY_ATTEMPTS,
    MINIMUM_AUTO_CONFIDENCE,
    PAYMENT_FAILURE_CASE_COUNT,
    PAYMENT_METHOD_WEIGHTS,
    PAYMENT_METHODS,
    RECOVERY_CASE_COUNT,
    SUBSCRIPTION_COUNT,
    TRANSACTION_AMOUNTS_MINOR,
    TRANSACTION_COUNT,
    demo_timestamp,
    demo_uuid,
)
from app.domain.enums import (
    AuditActorType,
    FailureCategory,
    RecoveryActionStatus,
    RecoveryActionType,
    RecoveryCaseStatus,
    RecoveryOutcomeType,
    UserRole,
    VerificationSource,
)
from app.recovery.erv import calculate_erv
from app.recovery.selection import select_candidate_row

TERMINAL_STATUSES = {
    RecoveryCaseStatus.RECOVERED.value,
    RecoveryCaseStatus.FAILED.value,
    RecoveryCaseStatus.STOPPED.value,
}

ANALYZED_STATUSES = {
    RecoveryCaseStatus.RECOMMENDED.value,
    RecoveryCaseStatus.AWAITING_APPROVAL.value,
    RecoveryCaseStatus.SCHEDULED.value,
    RecoveryCaseStatus.WAITING_FOR_OUTCOME.value,
    RecoveryCaseStatus.RECOVERED.value,
    RecoveryCaseStatus.FAILED.value,
    RecoveryCaseStatus.STOPPED.value,
}


@dataclass(frozen=True)
class OrganizationSpec:
    id: UUID
    name: str
    currency: str
    automation_enabled: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class UserProfileSpec:
    id: UUID
    organization_id: UUID
    auth_user_id: UUID
    role: str
    created_at: datetime


@dataclass(frozen=True)
class CustomerSpec:
    id: UUID
    organization_id: UUID
    external_id: str
    display_name: str
    email: str | None
    phone: str | None
    segment: str
    lifetime_value_minor: int
    is_synthetic: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class TransactionSpec:
    id: UUID
    organization_id: UUID
    customer_id: UUID
    provider: str
    provider_payment_id: str | None
    provider_order_id: str | None
    amount_minor: int
    currency: str
    status: str
    payment_method: str | None
    error_code: str | None
    error_reason: str | None
    error_source: str | None
    error_step: str | None
    error_description: str | None
    provider_created_at: datetime | None
    last_provider_event_at: datetime | None
    metadata: dict
    is_synthetic: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class SubscriptionSpec:
    id: UUID
    organization_id: UUID
    customer_id: UUID
    provider: str
    provider_subscription_id: str
    amount_minor: int
    currency: str
    status: str
    retry_count: int
    current_period_end: datetime | None
    next_charge_at: datetime | None
    last_provider_event_at: datetime | None
    metadata: dict
    is_synthetic: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class RecoveryCaseSpec:
    id: UUID
    organization_id: UUID
    customer_id: UUID
    transaction_id: UUID | None
    subscription_id: UUID | None
    invoice_id: UUID | None
    source_event_key: str
    case_type: str
    amount_at_risk_minor: int
    currency: str
    failure_category: str | None
    status: str
    priority_score: Decimal | None
    recovery_probability: Decimal | None
    expected_recoverable_minor: int | None
    current_analysis_run_id: UUID | None
    opened_at: datetime
    last_transition_at: datetime
    resolved_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime
    logical_key: str | None = None


@dataclass(frozen=True)
class RecommendationSpec:
    id: UUID
    organization_id: UUID
    case_id: UUID
    analysis_run_id: UUID
    action_type: str
    rank: int
    success_probability: Decimal
    expected_recovered_minor: int
    expected_value_minor: int
    erv_action_cost_minor: int
    erv_fatigue_penalty_minor: int
    erv_operational_risk_penalty_minor: int
    erv_delay_penalty_minor: int
    confidence: Decimal
    policy_eligible: bool
    requires_approval: bool
    policy_reasons: list[str]
    factors: list[dict[str, str]]
    model_version: str
    feature_schema_version: str
    created_at: datetime


@dataclass(frozen=True)
class ActionSpec:
    id: UUID
    organization_id: UUID
    case_id: UUID
    recommendation_id: UUID | None
    action_type: str
    status: str
    attempt_number: int
    requires_approval: bool
    approved_by: UUID | None
    approved_at: datetime | None
    idempotency_key: str
    request_fingerprint: str | None
    scheduled_for: datetime | None
    execution_started_at: datetime | None
    executed_at: datetime | None
    provider_reference: str | None
    provider_status: str | None
    error_category: str | None
    error_message: str | None
    metadata: dict
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class OutcomeSpec:
    id: UUID
    organization_id: UUID
    case_id: UUID
    outcome: str
    recovered_amount_minor: int
    recovered_payment_id: str | None
    verification_source: str
    verified_event_id: UUID | None
    recovered_at: datetime | None
    time_to_recovery_seconds: int | None
    metadata: dict
    created_at: datetime


@dataclass(frozen=True)
class AuditLogSpec:
    id: UUID
    organization_id: UUID
    case_id: UUID | None
    actor_type: str
    actor_id: str | None
    event_type: str
    summary: str
    evidence: dict
    created_at: datetime


@dataclass(frozen=True)
class MerchantPolicySpec:
    id: UUID
    organization_id: UUID
    auto_action_limit_minor: int
    max_recovery_attempts: int
    max_contacts_per_24h: int
    minimum_auto_confidence: Decimal
    cooldown_minutes: int
    automation_enabled: bool
    allowed_action_types: list[str]
    created_at: datetime
    updated_at: datetime


@dataclass
class DemoSeedSpec:
    organization: OrganizationSpec
    user_profiles: list[UserProfileSpec]
    customers: list[CustomerSpec]
    transactions: list[TransactionSpec]
    subscriptions: list[SubscriptionSpec]
    recovery_cases: list[RecoveryCaseSpec]
    recommendations: list[RecommendationSpec] = field(default_factory=list)
    actions: list[ActionSpec] = field(default_factory=list)
    outcomes: list[OutcomeSpec] = field(default_factory=list)
    audit_logs: list[AuditLogSpec] = field(default_factory=list)
    merchant_policy: MerchantPolicySpec | None = None


def _segment_for_index(index: int) -> str:
    if index < 35:
        return "REGULAR"
    if index < 51:
        return "HIGH_VALUE"
    if index < 61:
        return "NEW"
    return "VIP"


def _payment_method_for_index(index: int) -> str:
    bucket = index % sum(PAYMENT_METHOD_WEIGHTS)
    cumulative = 0
    for method, weight in zip(PAYMENT_METHODS, PAYMENT_METHOD_WEIGHTS, strict=True):
        cumulative += weight
        if bucket < cumulative:
            return method
    return PAYMENT_METHODS[-1]


def _amount_for_index(index: int) -> int:
    return TRANSACTION_AMOUNTS_MINOR[index % len(TRANSACTION_AMOUNTS_MINOR)]


def _failure_evidence(index: int, payment_method: str) -> tuple[str, str, str, str, str]:
    fixtures = [
        (
            "BAD_REQUEST_ERROR",
            "payment_rail_unavailable",
            "gateway",
            "payment_authorization",
            f"{payment_method} rail reported temporary downtime",
        ),
        (
            "BAD_REQUEST_ERROR",
            "insufficient_funds",
            "customer",
            "payment_authorization",
            "Customer account had insufficient balance",
        ),
        (
            "BAD_REQUEST_ERROR",
            "payment_authentication_failure",
            "customer",
            "payment_authentication",
            "Customer did not complete OTP authentication",
        ),
        (
            "BAD_REQUEST_ERROR",
            "bank_declined",
            "issuer",
            "payment_authorization",
            "Issuer bank declined the payment",
        ),
        (
            "BAD_REQUEST_ERROR",
            "expired_payment_method",
            "customer",
            "payment_authorization",
            "Saved payment method expired",
        ),
        (
            "BAD_REQUEST_ERROR",
            "mandate_failure",
            "gateway",
            "recurring_payment",
            "Recurring mandate could not be charged",
        ),
        (
            "SERVER_ERROR",
            "technical_failure",
            "gateway",
            "payment_processing",
            "Synthetic gateway timeout during authorization",
        ),
    ]
    return fixtures[index % len(fixtures)]


def _failure_category_for_index(index: int) -> str:
    categories = [
        FailureCategory.PAYMENT_RAIL_DOWNTIME.value,
        FailureCategory.INSUFFICIENT_FUNDS.value,
        FailureCategory.AUTHENTICATION_FAILURE.value,
        FailureCategory.BANK_OR_ISSUER_DECLINE.value,
        FailureCategory.EXPIRED_OR_INVALID_METHOD.value,
        FailureCategory.MANDATE_OR_RECURRING_FAILURE.value,
        FailureCategory.TECHNICAL_FAILURE.value,
        FailureCategory.UNKNOWN.value,
    ]
    return categories[index % len(categories)]


# Demo-only mapping for synthetic fixture provenance (not production normalization).
DEMO_ERROR_REASON_TO_FAILURE_CATEGORY: dict[str, str] = {
    "payment_rail_unavailable": FailureCategory.PAYMENT_RAIL_DOWNTIME.value,
    "insufficient_funds": FailureCategory.INSUFFICIENT_FUNDS.value,
    "payment_authentication_failure": FailureCategory.AUTHENTICATION_FAILURE.value,
    "bank_declined": FailureCategory.BANK_OR_ISSUER_DECLINE.value,
    "expired_payment_method": FailureCategory.EXPIRED_OR_INVALID_METHOD.value,
    "mandate_failure": FailureCategory.MANDATE_OR_RECURRING_FAILURE.value,
    "technical_failure": FailureCategory.TECHNICAL_FAILURE.value,
}

RESERVED_PAYMENT_TRANSACTION_INDICES = {0, 1}
RESERVED_SUBSCRIPTION_INDICES = {0}


def demo_failure_category_from_transaction(txn: TransactionSpec) -> str:
    if txn.error_reason is None:
        return FailureCategory.UNKNOWN.value
    return DEMO_ERROR_REASON_TO_FAILURE_CATEGORY.get(
        txn.error_reason,
        FailureCategory.UNKNOWN.value,
    )


def demo_source_event_key(
    case_type: str,
    transaction_id: UUID | None,
    subscription_id: UUID | None,
) -> str:
    if case_type == "PAYMENT_FAILURE":
        assert transaction_id is not None
        return f"synthetic:payment_failure:{transaction_id}"
    assert subscription_id is not None
    return f"synthetic:subscription_failure:{subscription_id}"


def _subscription_metadata_for_index(index: int, status: str) -> dict:
    if index == 0:
        return {
            "source": "SYNTHETIC_DEMO",
            "previous_failure_reason": "mandate_failure",
            "previous_failure_category": FailureCategory.MANDATE_OR_RECURRING_FAILURE.value,
            "recovered": True,
        }
    if status in {"PENDING", "HALTED"}:
        reason = (
            "mandate_failure"
            if index % 2 == 0
            else "insufficient_funds"
        )
        category = DEMO_ERROR_REASON_TO_FAILURE_CATEGORY.get(
            reason,
            FailureCategory.UNKNOWN.value,
        )
        return {
            "source": "SYNTHETIC_DEMO",
            "last_failure_reason": reason,
            "last_failure_category": category,
        }
    return {"source": "SYNTHETIC_DEMO"}


#: Deterministic time-to-recovery spread, in seconds.
#:
#: Every recovered case previously carried exactly 86400, so "Avg. time to
#: recover" rendered as a suspiciously clean `1d` -- internally consistent and
#: obviously synthetic to anyone who looked twice. These buckets are shaped like
#: real recovery behaviour: a heavy cluster inside the first few hours (a
#: customer who acts on a payment link does so quickly), a long tail out to
#: three days, and nothing instantaneous.
#:
#: Still synthetic, and still labelled as such everywhere it surfaces. The point
#: is not to imply measurement, it is to stop a fabricated constant from
#: masquerading as one.
_RECOVERY_LATENCY_BUCKETS_SECONDS: tuple[int, ...] = (
    23 * 60,
    47 * 60,
    1 * 3600 + 38 * 60,
    2 * 3600 + 54 * 60,
    4 * 3600 + 11 * 60,
    6 * 3600 + 32 * 60,
    9 * 3600 + 17 * 60,
    13 * 3600 + 45 * 60,
    19 * 3600 + 8 * 60,
    26 * 3600 + 22 * 60,
    35 * 3600 + 50 * 60,
    52 * 3600 + 6 * 60,
    71 * 3600 + 29 * 60,
)


def _time_to_recovery_seconds(case_id: UUID) -> int:
    """Pick this case's recovery latency from the deterministic spread.

    Keyed on the case's own UUID, so the value is stable across seed runs and
    independent of iteration order.
    """
    return _RECOVERY_LATENCY_BUCKETS_SECONDS[
        case_id.int % len(_RECOVERY_LATENCY_BUCKETS_SECONDS)
    ]


def _build_case_status_sequence() -> list[str]:
    sequence: list[str] = []
    for status, count in CASE_STATE_COUNTS.items():
        sequence.extend([status] * count)
    return sequence


def _named_case_overrides() -> dict[str, dict[str, object]]:
    return {
        DEMO_CASE_UPI_DOWNTIME: {
            "id": DEMO_CASE_UPI_DOWNTIME_ID,
            "status": RecoveryCaseStatus.RECOMMENDED.value,
            "case_type": "PAYMENT_FAILURE",
            "amount_at_risk_minor": 499900,
            "failure_category": FailureCategory.PAYMENT_RAIL_DOWNTIME.value,
            "analysis_run_id": DEMO_ANALYSIS_UPI_DOWNTIME_ID,
            "customer_index": 4,
            "transaction_index": 0,
        },
        DEMO_CASE_HIGH_VALUE_APPROVAL: {
            "id": DEMO_CASE_HIGH_VALUE_APPROVAL_ID,
            "status": RecoveryCaseStatus.AWAITING_APPROVAL.value,
            "case_type": "PAYMENT_FAILURE",
            "amount_at_risk_minor": 3500000,
            "failure_category": FailureCategory.INSUFFICIENT_FUNDS.value,
            "analysis_run_id": DEMO_ANALYSIS_HIGH_VALUE_ID,
            "customer_index": 8,
            "transaction_index": 1,
        },
        DEMO_CASE_RECOVERED_HISTORY: {
            "id": DEMO_CASE_RECOVERED_HISTORY_ID,
            "status": RecoveryCaseStatus.RECOVERED.value,
            "case_type": "SUBSCRIPTION_FAILURE",
            "amount_at_risk_minor": 149900,
            "failure_category": FailureCategory.MANDATE_OR_RECURRING_FAILURE.value,
            "analysis_run_id": DEMO_ANALYSIS_RECOVERED_HISTORY_ID,
            "customer_index": 12,
            "subscription_index": 0,
        },
    }


def seed_analysis_timestamp(case: RecoveryCaseSpec) -> datetime:
    """When a seeded case is treated as having been analysed.

    Derived from the case's own `opened_at` rather than wall-clock now, so the
    features that depend on elapsed time (`hours_since_failure` above all) are
    identical on every seed run.
    """
    return case.opened_at.replace(minute=min(case.opened_at.minute + 5, 59))


def _recommendations_for_case(
    case: RecoveryCaseSpec,
    analysis_run_id: UUID,
    logical_key: str | None = None,
    created_at: datetime | None = None,
) -> list[RecommendationSpec]:
    amount = case.amount_at_risk_minor
    created_at = created_at or seed_analysis_timestamp(case)
    candidates: list[tuple[str, Decimal, int, bool, bool, list[str], list[dict[str, str]]]] = []

    if logical_key == DEMO_CASE_UPI_DOWNTIME:
        candidates = [
            (
                RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD.value,
                Decimal("0.82"),
                1,
                True,
                False,
                [],
                [
                    {
                        "code": "ACTIVE_UPI_DOWNTIME",
                        "impact": "HIGH",
                        "source": "SYNTHETIC_DEMO",
                    }
                ],
            ),
            (
                RecoveryActionType.CREATE_PAYMENT_LINK.value,
                Decimal("0.74"),
                2,
                True,
                False,
                [],
                [
                    {
                        "code": "HIGH_VALUE_CUSTOMER",
                        "impact": "MEDIUM",
                        "source": "SYNTHETIC_DEMO",
                    }
                ],
            ),
            (
                RecoveryActionType.WAIT.value,
                Decimal("0.61"),
                3,
                True,
                False,
                [],
                [
                    {
                        "code": "RAIL_RECOVERY_WINDOW",
                        "impact": "MEDIUM",
                        "source": "SYNTHETIC_DEMO",
                    }
                ],
            ),
            (
                RecoveryActionType.RETRY_SAME_METHOD.value,
                Decimal("0.22"),
                4,
                False,
                False,
                ["ACTIVE_PAYMENT_RAIL_DOWNTIME"],
                [
                    {
                        "code": "ACTIVE_UPI_DOWNTIME",
                        "impact": "HIGH",
                        "source": "SYNTHETIC_DEMO",
                    }
                ],
            ),
        ]
    elif logical_key == DEMO_CASE_HIGH_VALUE_APPROVAL:
        candidates = [
            (
                RecoveryActionType.CREATE_PAYMENT_LINK.value,
                Decimal("0.79"),
                1,
                True,
                True,
                ["AMOUNT_ABOVE_AUTO_ACTION_LIMIT"],
                [
                    {
                        "code": "HIGH_VALUE_PAYMENT",
                        "impact": "HIGH",
                        "source": "SYNTHETIC_DEMO",
                    }
                ],
            ),
            (
                RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD.value,
                Decimal("0.71"),
                2,
                True,
                True,
                ["AMOUNT_ABOVE_AUTO_ACTION_LIMIT"],
                [
                    {
                        "code": "LOYAL_CUSTOMER",
                        "impact": "MEDIUM",
                        "source": "SYNTHETIC_DEMO",
                    }
                ],
            ),
            (
                RecoveryActionType.ESCALATE_TO_HUMAN.value,
                Decimal("0.66"),
                3,
                True,
                True,
                ["AMOUNT_ABOVE_AUTO_ACTION_LIMIT"],
                [
                    {
                        "code": "MANUAL_REVIEW_RECOMMENDED",
                        "impact": "MEDIUM",
                        "source": "SYNTHETIC_DEMO",
                    }
                ],
            ),
        ]
    elif logical_key == DEMO_CASE_RECOVERED_HISTORY:
        candidates = [
            (
                RecoveryActionType.RETRY_SAME_METHOD.value,
                Decimal("0.68"),
                1,
                True,
                False,
                [],
                [
                    {
                        "code": "SUBSCRIPTION_RETRY_WINDOW",
                        "impact": "MEDIUM",
                        "source": "SYNTHETIC_DEMO",
                    }
                ],
            ),
            (
                RecoveryActionType.CREATE_PAYMENT_LINK.value,
                Decimal("0.55"),
                2,
                True,
                False,
                [],
                [
                    {
                        "code": "ALTERNATE_COLLECTION",
                        "impact": "LOW",
                        "source": "SYNTHETIC_DEMO",
                    }
                ],
            ),
            (
                RecoveryActionType.WAIT.value,
                Decimal("0.40"),
                3,
                True,
                False,
                [],
                [
                    {
                        "code": "MANDATE_COOLDOWN",
                        "impact": "LOW",
                        "source": "SYNTHETIC_DEMO",
                    }
                ],
            ),
        ]
    else:
        primary = [
            RecoveryActionType.RETRY_SAME_METHOD.value,
            RecoveryActionType.CREATE_PAYMENT_LINK.value,
            RecoveryActionType.REQUEST_ALTERNATE_PAYMENT_METHOD.value,
            RecoveryActionType.WAIT.value,
        ]
        base_prob = Decimal("0.72") - Decimal(str((case.id.int % 7) * 0.03))
        for rank, action in enumerate(primary[:3], start=1):
            prob = max(Decimal("0.15"), base_prob - Decimal(str((rank - 1) * 0.08)))
            candidates.append(
                (
                    action,
                    prob,
                    rank,
                    rank != 4,
                    case.amount_at_risk_minor > AUTO_ACTION_LIMIT_MINOR,
                    ["AMOUNT_ABOVE_AUTO_ACTION_LIMIT"]
                    if case.amount_at_risk_minor > AUTO_ACTION_LIMIT_MINOR and rank == 1
                    else [],
                    [
                        {
                            "code": case.failure_category or "UNKNOWN",
                            "impact": "MEDIUM",
                            "source": "SYNTHETIC_DEMO",
                        }
                    ],
                )
            )

    recommendations: list[RecommendationSpec] = []
    for action_type, prob, rank, eligible, requires_approval, reasons, factors in candidates:
        # Run the real ERV calculation rather than setting expected value equal
        # to expected recovery. The old shortcut made "Expected recovery value"
        # and "Expected recovered amount" print the identical number, which is
        # wrong by the engine's own definition: expected value is net of action
        # cost and the risk and delay penalties.
        breakdown = calculate_erv(
            action=RecoveryActionType(action_type),
            amount_at_risk_minor=amount,
            success_probability=prob,
            contacts_last_24h=0,
        )
        expected_recovered = breakdown.expected_recovered_minor
        recommendations.append(
            RecommendationSpec(
                id=demo_uuid(f"recommendation:{case.id}:{analysis_run_id}:{action_type}"),
                organization_id=case.organization_id,
                case_id=case.id,
                analysis_run_id=analysis_run_id,
                action_type=action_type,
                rank=rank,
                success_probability=prob,
                expected_recovered_minor=expected_recovered,
                expected_value_minor=breakdown.expected_value_minor,
                erv_action_cost_minor=breakdown.action_cost_minor,
                erv_fatigue_penalty_minor=breakdown.fatigue_penalty_minor,
                erv_operational_risk_penalty_minor=breakdown.operational_risk_penalty_minor,
                erv_delay_penalty_minor=breakdown.delay_penalty_minor,
                confidence=min(Decimal("0.95"), prob + Decimal("0.05")),
                policy_eligible=eligible,
                requires_approval=requires_approval,
                policy_reasons=reasons,
                factors=factors,
                model_version="demo-heuristic-v1",
                feature_schema_version="demo-seed-v1",
                created_at=created_at,
            )
        )
    return recommendations


#: Signature of a per-case recommendation builder.
#:
#: `build_demo_seed_spec` is pure and has no database, but real model inference
#: needs one: features are read from the persisted case, customer, transaction
#: and subscription rows. Injecting the builder lets `seed_demo_database` run
#: the factory once to lay down the world, analyse the persisted cases with the
#: production engine, then run the factory again with a builder that returns
#: those real results -- so seeded actions, outcomes and audit entries are all
#: derived from what the engine actually selected.
#:
#: The default builder produces the canned table below. It is retained as an
#: explicit fallback for pure, database-free contexts (most factory unit tests),
#: not as a path any deployed seed takes.
CaseRecommendationBuilder = Callable[
    [RecoveryCaseSpec, UUID, str | None, datetime], list[RecommendationSpec]
]


def build_demo_seed_spec(
    *,
    recommendations_for_case: CaseRecommendationBuilder | None = None,
) -> DemoSeedSpec:
    org_created = demo_timestamp(days_offset=-120)
    organization = OrganizationSpec(
        id=DEMO_ORGANIZATION_ID,
        name=DEMO_ORGANIZATION_NAME,
        currency=DEMO_ORGANIZATION_CURRENCY,
        automation_enabled=True,
        created_at=org_created,
        updated_at=org_created,
    )

    user_profiles = [
        UserProfileSpec(
            id=DEMO_USER_ADMIN_ID,
            organization_id=DEMO_ORGANIZATION_ID,
            auth_user_id=DEMO_AUTH_USER_ADMIN_ID,
            role=UserRole.ADMIN.value,
            created_at=org_created,
        ),
        UserProfileSpec(
            id=DEMO_USER_OPERATOR_ID,
            organization_id=DEMO_ORGANIZATION_ID,
            auth_user_id=DEMO_AUTH_USER_OPERATOR_ID,
            role=UserRole.OPERATOR.value,
            created_at=org_created,
        ),
        UserProfileSpec(
            id=DEMO_USER_ANALYST_ID,
            organization_id=DEMO_ORGANIZATION_ID,
            auth_user_id=DEMO_AUTH_USER_ANALYST_ID,
            role=UserRole.ANALYST.value,
            created_at=org_created,
        ),
    ]

    customers: list[CustomerSpec] = []
    for index in range(CUSTOMER_COUNT):
        first = FIRST_NAMES[index % len(FIRST_NAMES)]
        last = LAST_NAMES[(index // len(FIRST_NAMES)) % len(LAST_NAMES)]
        created = demo_timestamp(days_offset=-90 + (index % 60))
        ltv = _amount_for_index(index) * (3 + index % 12)
        customers.append(
            CustomerSpec(
                id=demo_uuid(f"customer:{index + 1:04d}"),
                organization_id=DEMO_ORGANIZATION_ID,
                external_id=f"demo-customer-{index + 1:04d}",
                display_name=f"{first} {last}",
                email=f"{first.lower()}.{last.lower()}{index + 1}@example.com",
                phone=f"+91-90000-{index + 1:05d}" if index % 3 == 0 else None,
                segment=_segment_for_index(index),
                lifetime_value_minor=ltv,
                is_synthetic=True,
                created_at=created,
                updated_at=created,
            )
        )

    transactions: list[TransactionSpec] = []
    failed_transaction_indices: list[int] = []
    for index in range(TRANSACTION_COUNT):
        customer = customers[index % CUSTOMER_COUNT]
        payment_method = _payment_method_for_index(index)
        amount = _amount_for_index(index)
        is_failed = index < 120 or index in (0, 1)
        status = "failed" if is_failed else "captured"
        created = demo_timestamp(days_offset=-60 + (index % 55), hours_offset=-(index % 12))
        error_fields = (None, None, None, None, None)
        if is_failed:
            failed_transaction_indices.append(index)
            error_fields = _failure_evidence(index, payment_method)
        transactions.append(
            TransactionSpec(
                id=demo_uuid(f"transaction:{index + 1:04d}"),
                organization_id=DEMO_ORGANIZATION_ID,
                customer_id=customer.id,
                provider="SYNTHETIC",
                provider_payment_id=f"synthetic-pay-{index + 1:05d}",
                provider_order_id=f"synthetic-order-{index + 1:05d}",
                amount_minor=amount if index not in (0, 1) else (499900 if index == 0 else 3500000),
                currency=DEMO_ORGANIZATION_CURRENCY,
                status=status,
                payment_method=payment_method,
                error_code=error_fields[0],
                error_reason=error_fields[1],
                error_source=error_fields[2],
                error_step=error_fields[3],
                error_description=error_fields[4],
                provider_created_at=created,
                last_provider_event_at=created,
                metadata={"source": "SYNTHETIC_DEMO"},
                is_synthetic=True,
                created_at=created,
                updated_at=created,
            )
        )

    subscriptions: list[SubscriptionSpec] = []
    subscription_statuses = ("ACTIVE", "PENDING", "HALTED")
    for index in range(SUBSCRIPTION_COUNT):
        customer = customers[(index * 2) % CUSTOMER_COUNT]
        if index == 0:
            status = "ACTIVE"
        else:
            status = subscription_statuses[index % len(subscription_statuses)]
        created = demo_timestamp(days_offset=-45 + (index % 30))
        amount = _amount_for_index(index + 5)
        subscriptions.append(
            SubscriptionSpec(
                id=demo_uuid(f"subscription:{index + 1:04d}"),
                organization_id=DEMO_ORGANIZATION_ID,
                customer_id=customer.id,
                provider="SYNTHETIC",
                provider_subscription_id=f"synthetic-sub-{index + 1:04d}",
                amount_minor=amount if index != 0 else 149900,
                currency=DEMO_ORGANIZATION_CURRENCY,
                status=status,
                retry_count=index % 4,
                current_period_end=demo_timestamp(days_offset=15 + index),
                next_charge_at=demo_timestamp(days_offset=20 + index),
                last_provider_event_at=created,
                metadata=_subscription_metadata_for_index(index, status),
                is_synthetic=True,
                created_at=created,
                updated_at=created,
            )
        )

    generic_failed_transaction_indices = [
        index
        for index in failed_transaction_indices
        if index not in RESERVED_PAYMENT_TRANSACTION_INDICES
    ]
    generic_subscription_indices = [
        index for index in range(SUBSCRIPTION_COUNT) if index not in RESERVED_SUBSCRIPTION_INDICES
    ]

    named_overrides = _named_case_overrides()
    status_pool = _build_case_status_sequence()
    named_keys = [
        DEMO_CASE_UPI_DOWNTIME,
        DEMO_CASE_HIGH_VALUE_APPROVAL,
        DEMO_CASE_RECOVERED_HISTORY,
    ]
    named_case_statuses = {
        0: str(named_overrides[DEMO_CASE_UPI_DOWNTIME]["status"]),
        1: str(named_overrides[DEMO_CASE_HIGH_VALUE_APPROVAL]["status"]),
        2: str(named_overrides[DEMO_CASE_RECOVERED_HISTORY]["status"]),
    }
    for named_status in named_case_statuses.values():
        status_pool.remove(named_status)

    recovery_cases: list[RecoveryCaseSpec] = []
    payment_case_cursor = 0
    subscription_case_cursor = 0
    pool_cursor = 0

    for case_index in range(RECOVERY_CASE_COUNT):
        logical_key = named_keys[case_index] if case_index < len(named_keys) else None
        override = named_overrides[logical_key] if logical_key else {}

        if logical_key:
            status = str(override["status"])
            case_type = str(override["case_type"])
            amount = int(override["amount_at_risk_minor"])
            failure_category = str(override["failure_category"])
            case_id = override["id"]  # type: ignore[assignment]
            if case_type == "PAYMENT_FAILURE":
                txn_index = int(override["transaction_index"])
                customer = customers[int(override["customer_index"])]
                transaction_id = transactions[txn_index].id
                subscription_id = None
            else:
                sub_index = int(override["subscription_index"])
                customer = customers[int(override["customer_index"])]
                transaction_id = None
                subscription_id = subscriptions[sub_index].id
        else:
            status = status_pool[pool_cursor]
            pool_cursor += 1
            is_payment = case_index <= PAYMENT_FAILURE_CASE_COUNT and case_index != 2
            case_type = "PAYMENT_FAILURE" if is_payment else "SUBSCRIPTION_FAILURE"
            case_id = demo_uuid(f"case:{case_index + 1:03d}")
            if is_payment:
                txn_index = generic_failed_transaction_indices[payment_case_cursor]
                payment_case_cursor += 1
                txn = transactions[txn_index]
                customer = next(c for c in customers if c.id == txn.customer_id)
                transaction_id = txn.id
                subscription_id = None
                amount = txn.amount_minor
                failure_category = demo_failure_category_from_transaction(txn)
            else:
                sub_index = generic_subscription_indices[subscription_case_cursor]
                subscription_case_cursor += 1
                sub = subscriptions[sub_index]
                customer = next(c for c in customers if c.id == sub.customer_id)
                transaction_id = None
                subscription_id = sub.id
                amount = sub.amount_minor
                failure_category = _failure_category_for_index(case_index)

        opened_at = demo_timestamp(
            days_offset=-30 + (case_index % 25),
            hours_offset=-(case_index % 8),
        )
        is_terminal = status in TERMINAL_STATUSES
        resolved_at = (
            demo_timestamp(days_offset=-5 + (case_index % 4)) if is_terminal else None
        )
        last_transition_at = resolved_at or demo_timestamp(
            days_offset=-2,
            hours_offset=-(case_index % 6),
        )

        analysis_run_id = None
        if status in ANALYZED_STATUSES:
            if logical_key:
                analysis_run_id = override["analysis_run_id"]  # type: ignore[assignment]
            else:
                analysis_run_id = demo_uuid(f"analysis:{case_id}")

        rank1_prob = Decimal("0.72")
        priority_score = (
            Decimal("0.80")
            if logical_key
            else Decimal(str(0.45 + (case_index % 40) / 100))
        )
        recovery_cases.append(
            RecoveryCaseSpec(
                id=case_id,
                organization_id=DEMO_ORGANIZATION_ID,
                customer_id=customer.id,
                transaction_id=transaction_id,
                subscription_id=subscription_id,
                invoice_id=None,
                source_event_key=demo_source_event_key(case_type, transaction_id, subscription_id),
                case_type=case_type,
                amount_at_risk_minor=amount,
                currency=DEMO_ORGANIZATION_CURRENCY,
                failure_category=failure_category,
                status=status,
                priority_score=priority_score,
                recovery_probability=rank1_prob if analysis_run_id else None,
                expected_recoverable_minor=int(amount * rank1_prob) if analysis_run_id else None,
                current_analysis_run_id=analysis_run_id,
                opened_at=opened_at,
                last_transition_at=last_transition_at,
                resolved_at=resolved_at,
                version=1,
                created_at=opened_at,
                updated_at=last_transition_at,
                logical_key=logical_key,
            )
        )

    recommendations: list[RecommendationSpec] = []
    actions: list[ActionSpec] = []
    outcomes: list[OutcomeSpec] = []
    audit_logs: list[AuditLogSpec] = []

    for case in recovery_cases:
        audit_logs.append(
            AuditLogSpec(
                id=demo_uuid(f"audit:{case.id}:created"),
                organization_id=case.organization_id,
                case_id=case.id,
                actor_type=AuditActorType.SYSTEM.value,
                actor_id="seed",
                event_type="CASE_CREATED",
                summary="Synthetic demo recovery case opened from seeded provider evidence.",
                evidence={
                    "failure_category": case.failure_category,
                    "source": "SYNTHETIC_DEMO",
                },
                created_at=case.opened_at,
            )
        )

        if case.current_analysis_run_id is None:
            continue

        analysis_at = seed_analysis_timestamp(case)
        build_recommendations = recommendations_for_case or _recommendations_for_case
        case_recs = build_recommendations(
            case,
            case.current_analysis_run_id,
            case.logical_key,
            analysis_at,
        )
        recommendations.extend(case_recs)
        rank1 = next(rec for rec in case_recs if rec.rank == 1)
        # Seeded history records what RevLoop DID, so it follows the selected
        # action, not rank 1. Those diverge whenever the model's first choice is
        # advisory. Building history from rank 1 is what made the dashboard
        # attribute nearly all recovered revenue to RETRY_SAME_METHOD -- an
        # action the product never executes -- which would not survive the first
        # follow-up question from anyone with a payments background.
        selected = select_candidate_row(case_recs) or rank1

        audit_logs.append(
            AuditLogSpec(
                id=demo_uuid(f"audit:{case.id}:analysis"),
                organization_id=case.organization_id,
                case_id=case.id,
                actor_type=AuditActorType.MODEL.value,
                actor_id="demo-heuristic-v1",
                event_type="ANALYSIS_COMPLETED",
                summary=(
                    f"Analysis selected {selected.action_type}; "
                    f"model ranked {rank1.action_type} first."
                ),
                evidence={
                    "analysis_run_id": str(case.current_analysis_run_id),
                    "selected_action": selected.action_type,
                    "top_ranked_action": rank1.action_type,
                    "source": "SYNTHETIC_DEMO",
                },
                created_at=analysis_at,
            )
        )

        if case.status == RecoveryCaseStatus.AWAITING_APPROVAL.value:
            audit_logs.append(
                AuditLogSpec(
                    id=demo_uuid(f"audit:{case.id}:approval"),
                    organization_id=case.organization_id,
                    case_id=case.id,
                    actor_type=AuditActorType.SYSTEM.value,
                    actor_id="policy-engine",
                    event_type="APPROVAL_REQUESTED",
                    summary="Recovery action requires operator approval before execution.",
                    evidence={
                        "policy_reasons": selected.policy_reasons,
                        "source": "SYNTHETIC_DEMO",
                    },
                    created_at=analysis_at.replace(minute=min(analysis_at.minute + 10, 59)),
                )
            )

        # AWAITING_APPROVAL is included deliberately. A case in that state is,
        # by definition, waiting on a specific action -- but the seed used to
        # create no action row for it, so `latest_action` was null, the UI's
        # `canApprove` (which requires a non-null action) stayed false, and the
        # approval flow had no reachable surface anywhere in the demo. The state
        # was internally incoherent: the case claimed to be awaiting approval of
        # nothing.
        if case.status in {
            RecoveryCaseStatus.AWAITING_APPROVAL.value,
            RecoveryCaseStatus.SCHEDULED.value,
            RecoveryCaseStatus.WAITING_FOR_OUTCOME.value,
            RecoveryCaseStatus.RECOVERED.value,
            RecoveryCaseStatus.FAILED.value,
            RecoveryCaseStatus.STOPPED.value,
        }:
            attempt = 1
            action_status = RecoveryActionStatus.SCHEDULED.value
            executed_at = None
            if case.status == RecoveryCaseStatus.AWAITING_APPROVAL.value:
                action_status = RecoveryActionStatus.PENDING_APPROVAL.value
            elif case.status == RecoveryCaseStatus.WAITING_FOR_OUTCOME.value:
                action_status = RecoveryActionStatus.UNKNOWN.value
            elif case.status == RecoveryCaseStatus.RECOVERED.value:
                action_status = RecoveryActionStatus.SUCCEEDED.value
                executed_at = case.resolved_at
            elif case.status == RecoveryCaseStatus.FAILED.value:
                action_status = RecoveryActionStatus.FAILED.value
                executed_at = case.resolved_at
            elif case.status == RecoveryCaseStatus.STOPPED.value:
                action_status = RecoveryActionStatus.CANCELLED.value
                executed_at = case.resolved_at

            action_created = analysis_at.replace(minute=min(analysis_at.minute + 20, 59))
            actions.append(
                ActionSpec(
                    id=demo_uuid(f"action:{case.id}:{attempt}"),
                    organization_id=case.organization_id,
                    case_id=case.id,
                    recommendation_id=selected.id,
                    action_type=selected.action_type,
                    status=action_status,
                    attempt_number=attempt,
                    requires_approval=(
                        True
                        if case.status == RecoveryCaseStatus.AWAITING_APPROVAL.value
                        else selected.requires_approval
                    ),
                    # An action still awaiting approval has not been approved,
                    # so these stay null. Filling them in would have the row
                    # claim an approval that never happened.
                    approved_by=(
                        None
                        if case.status == RecoveryCaseStatus.AWAITING_APPROVAL.value
                        else (DEMO_AUTH_USER_OPERATOR_ID if selected.requires_approval else None)
                    ),
                    approved_at=(
                        None
                        if case.status == RecoveryCaseStatus.AWAITING_APPROVAL.value
                        else (action_created if selected.requires_approval else None)
                    ),
                    idempotency_key=f"recovery:{case.id}:{attempt}:{selected.action_type}",
                    request_fingerprint=f"demo-{case.id}-{attempt}",
                    scheduled_for=action_created,
                    execution_started_at=executed_at,
                    executed_at=executed_at,
                    provider_reference=(
                        None
                        if case.status == RecoveryCaseStatus.AWAITING_APPROVAL.value
                        else f"synthetic-action-{case.id}"
                    ),
                    provider_status=(
                        None
                        if case.status == RecoveryCaseStatus.AWAITING_APPROVAL.value
                        else action_status.lower()
                    ),
                    error_category=None,
                    error_message=None,
                    metadata={"source": "SYNTHETIC_DEMO"},
                    created_at=action_created,
                    updated_at=executed_at or action_created,
                )
            )

        if case.status in TERMINAL_STATUSES:
            if case.status == RecoveryCaseStatus.RECOVERED.value:
                outcome_type = RecoveryOutcomeType.RECOVERED.value
                recovered_amount = case.amount_at_risk_minor
                recovered_at = case.resolved_at
            elif case.status == RecoveryCaseStatus.FAILED.value:
                outcome_type = RecoveryOutcomeType.NOT_RECOVERED.value
                recovered_amount = 0
                recovered_at = None
            else:
                outcome_type = RecoveryOutcomeType.STOPPED.value
                recovered_amount = 0
                recovered_at = None

            outcomes.append(
                OutcomeSpec(
                    id=demo_uuid(f"outcome:{case.id}"),
                    organization_id=case.organization_id,
                    case_id=case.id,
                    outcome=outcome_type,
                    recovered_amount_minor=recovered_amount,
                    recovered_payment_id=(
                        f"synthetic-recovered-{case.id}" if recovered_amount else None
                    ),
                    verification_source=VerificationSource.SIMULATED_BATCH.value,
                    verified_event_id=None,
                    recovered_at=recovered_at,
                    time_to_recovery_seconds=(
                        _time_to_recovery_seconds(case.id) if recovered_at else None
                    ),
                    metadata={"source": "SYNTHETIC_DEMO"},
                    created_at=case.resolved_at or case.last_transition_at,
                )
            )

            terminal_event = {
                RecoveryCaseStatus.RECOVERED.value: "CASE_RECOVERED",
                RecoveryCaseStatus.FAILED.value: "CASE_FAILED",
                RecoveryCaseStatus.STOPPED.value: "CASE_STOPPED",
            }[case.status]
            audit_logs.append(
                AuditLogSpec(
                    id=demo_uuid(f"audit:{case.id}:terminal"),
                    organization_id=case.organization_id,
                    case_id=case.id,
                    actor_type=AuditActorType.SYSTEM.value,
                    actor_id="outcome-verifier",
                    event_type=terminal_event,
                    summary=f"Synthetic demo case reached terminal state {case.status}.",
                    evidence={"source": "SYNTHETIC_DEMO", "outcome": outcome_type},
                    created_at=case.resolved_at or case.last_transition_at,
                )
            )

        if case.logical_key == DEMO_CASE_RECOVERED_HISTORY:
            timeline_events = [
                (
                    "FAILURE_NORMALIZED",
                    "Subscription failure normalized to mandate/recurring category.",
                ),
                ("ACTION_SCHEDULED", "Recovery retry scheduled after synthetic analysis."),
                ("ACTION_EXECUTION_STARTED", "Synthetic recovery action execution started."),
                ("ACTION_SUCCEEDED", "Synthetic recovery action completed successfully."),
                ("OUTCOME_VERIFIED", "Simulated batch verification confirmed recovered payment."),
            ]
            for offset, (event_type, summary) in enumerate(timeline_events, start=1):
                audit_logs.append(
                    AuditLogSpec(
                        id=demo_uuid(f"audit:{case.id}:timeline:{offset}"),
                        organization_id=case.organization_id,
                        case_id=case.id,
                        actor_type=AuditActorType.SYSTEM.value,
                        actor_id="seed",
                        event_type=event_type,
                        summary=summary,
                        evidence={"source": "SYNTHETIC_DEMO"},
                        created_at=demo_timestamp(days_offset=-20 + offset, hours_offset=offset),
                    )
                )

    merchant_policy = MerchantPolicySpec(
        id=DEMO_MERCHANT_POLICY_ID,
        organization_id=DEMO_ORGANIZATION_ID,
        auto_action_limit_minor=AUTO_ACTION_LIMIT_MINOR,
        max_recovery_attempts=MAX_RECOVERY_ATTEMPTS,
        max_contacts_per_24h=MAX_CONTACTS_PER_24H,
        minimum_auto_confidence=MINIMUM_AUTO_CONFIDENCE,
        cooldown_minutes=COOLDOWN_MINUTES,
        automation_enabled=True,
        allowed_action_types=ALLOWED_ACTION_TYPES,
        created_at=org_created,
        updated_at=org_created,
    )

    assert len(recovery_cases) == RECOVERY_CASE_COUNT
    assert INVOICE_COUNT == 0

    return DemoSeedSpec(
        organization=organization,
        user_profiles=user_profiles,
        customers=customers,
        transactions=transactions,
        subscriptions=subscriptions,
        recovery_cases=recovery_cases,
        recommendations=recommendations,
        actions=actions,
        outcomes=outcomes,
        audit_logs=sorted(audit_logs, key=lambda entry: (entry.case_id or "", entry.created_at)),
        merchant_policy=merchant_policy,
    )
