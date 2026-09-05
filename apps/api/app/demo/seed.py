"""Persist deterministic demo seed data and perform tenant-scoped reset."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.db.session import _build_engine, get_session_factory
from app.demo.analysis_seed import (
    SeedAnalysisError,
    SeededAnalysis,
    analyse_seeded_cases,
)
from app.demo.constants import (
    DEMO_AUTH_USER_ADMIN_ID,
    DEMO_AUTH_USER_ANALYST_ID,
    DEMO_AUTH_USER_OPERATOR_ID,
    DEMO_ORGANIZATION_ID,
    demo_uuid,
)
from app.demo.factory import (
    DemoSeedSpec,
    RecommendationSpec,
    RecoveryCaseSpec,
    build_demo_seed_spec,
    seed_analysis_timestamp,
)
from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.merchant_policy import MerchantPolicy
from app.models.organization import Organization
from app.models.recovery_action import RecoveryAction
from app.models.recovery_case import RecoveryCase
from app.models.recovery_outcome import RecoveryOutcome
from app.models.recovery_recommendation import RecoveryRecommendation
from app.models.subscription import Subscription
from app.models.transaction import Transaction
from app.models.user_profile import UserProfile
from app.models.webhook_event import WebhookEvent

REQUIRED_TABLES = frozenset(
    {
        "organizations",
        "user_profiles",
        "customers",
        "transactions",
        "subscriptions",
        "invoices",
        "recovery_cases",
        "recovery_recommendations",
        "recovery_actions",
        "recovery_outcomes",
        "webhook_events",
        "audit_logs",
        "merchant_policies",
    }
)


class SeedError(RuntimeError):
    pass


class ResetNotAllowedError(AppError, SeedError):
    """Reset was refused by a deliberate safety gate.

    Inherits `AppError` so the registered handler answers a documented `403`
    with a specific code, instead of falling through to the catch-all handler
    that reports every uncaught exception as an opaque `500 INTERNAL_ERROR`.
    It stays a `SeedError` as well, so callers that treat seeding failures as
    one family keep working.
    """

    def __init__(self, *, code: str, message: str) -> None:
        AppError.__init__(self, code=code, message=message, status_code=403)


#: `auth_user_id` values the seed itself creates. Any other profile row in the
#: demo organization was provisioned outside the seed (a real Supabase account
#: mapped to this tenant by hand) and must survive a reset -- see
#: `capture_external_user_profiles`.
SEED_MANAGED_AUTH_USER_IDS = frozenset(
    {DEMO_AUTH_USER_ADMIN_ID, DEMO_AUTH_USER_OPERATOR_ID, DEMO_AUTH_USER_ANALYST_ID}
)


@dataclass(frozen=True)
class PreservedUserProfile:
    """A demo-org profile row the seed does not own, captured across a reset."""

    id: UUID
    organization_id: UUID
    auth_user_id: UUID
    role: str
    created_at: datetime


@dataclass(frozen=True)
class SeedResult:
    created: bool
    already_exists: bool
    reset_performed: bool
    organization_id: str
    #: How many externally provisioned profiles were carried across the reset.
    preserved_user_profiles: int = 0


def assert_schema_ready(engine: Engine) -> None:
    table_names = set(inspect(engine).get_table_names())
    missing = sorted(REQUIRED_TABLES - table_names)
    if missing:
        raise SeedError(
            "Database schema is not ready. Run: alembic upgrade head. "
            f"Missing tables: {', '.join(missing)}"
        )


def assert_reset_allowed(settings: Settings) -> None:
    """Refuse a destructive reset unless it was deliberately enabled.

    Reset deletes and rebuilds the whole demo tenant, so it is gated twice.
    `DEMO_MODE` decides whether the demo surface exists at all; under
    `APP_ENV=production` a second, independent `DEMO_RESET_ENABLED` opt-in is
    required, so the destructive path cannot be reached by a flag that the
    deployed environment already has switched on for unrelated reasons.
    """
    if not settings.demo_mode:
        raise ResetNotAllowedError(
            code="DEMO_MODE_DISABLED",
            message="Reset refused: DEMO_MODE is not enabled.",
        )
    if settings.is_production and not settings.demo_reset_enabled:
        raise ResetNotAllowedError(
            code="DEMO_RESET_NOT_ENABLED",
            message=(
                "Reset refused: this deployment runs with APP_ENV=production and "
                "DEMO_RESET_ENABLED is not set. Reset destroys and rebuilds the demo "
                "tenant, so it requires an explicit opt-in beyond DEMO_MODE."
            ),
        )


def demo_organization_exists(session: Session) -> bool:
    return (
        session.execute(
            select(Organization.id).where(Organization.id == DEMO_ORGANIZATION_ID)
        ).scalar_one_or_none()
        is not None
    )


def capture_external_user_profiles(session: Session) -> list[PreservedUserProfile]:
    """Snapshot demo-org profile rows that the seed did not create.

    The seed owns exactly three synthetic `auth_user_id` values. Anything else
    in this organization maps a real Supabase account onto the demo tenant and
    was provisioned by hand, so wiping it would leave that account
    authenticated but unauthorized -- every request would answer
    `403 NO_ORGANIZATION_MEMBERSHIP` and the deployed app would be unusable
    until someone re-ran the provisioning SQL. Reset must not be able to lock
    out the account it is meant to serve.
    """
    rows = session.execute(
        select(UserProfile).where(
            UserProfile.organization_id == DEMO_ORGANIZATION_ID,
            UserProfile.auth_user_id.not_in(SEED_MANAGED_AUTH_USER_IDS),
        )
    ).scalars()
    return [
        PreservedUserProfile(
            id=row.id,
            organization_id=row.organization_id,
            auth_user_id=row.auth_user_id,
            role=row.role,
            created_at=row.created_at,
        )
        for row in rows
    ]


def restore_external_user_profiles(
    session: Session,
    profiles: list[PreservedUserProfile],
) -> int:
    """Re-insert profiles captured before the delete, after the reseed.

    Re-inserted with their original `id`, `auth_user_id`, `role` and
    `created_at`, so an account keeps the exact identity and permissions it had
    before the reset. A profile whose `auth_user_id` the reseed has since
    claimed is skipped rather than colliding with the
    `uq_user_profiles_auth_user_id` constraint; in that case the seeded row
    already grants the same organization.
    """
    seeded_auth_ids = set(
        session.execute(
            select(UserProfile.auth_user_id).where(
                UserProfile.organization_id == DEMO_ORGANIZATION_ID
            )
        ).scalars()
    )
    restored = 0
    for profile in profiles:
        if profile.auth_user_id in seeded_auth_ids:
            continue
        session.add(
            UserProfile(
                id=profile.id,
                organization_id=profile.organization_id,
                auth_user_id=profile.auth_user_id,
                role=profile.role,
                created_at=profile.created_at,
            )
        )
        restored += 1
    return restored


def delete_demo_tenant(session: Session) -> None:
    org_id = DEMO_ORGANIZATION_ID
    session.execute(delete(AuditLog).where(AuditLog.organization_id == org_id))
    session.execute(delete(RecoveryOutcome).where(RecoveryOutcome.organization_id == org_id))
    session.execute(delete(RecoveryAction).where(RecoveryAction.organization_id == org_id))
    session.execute(
        delete(RecoveryRecommendation).where(RecoveryRecommendation.organization_id == org_id)
    )
    session.execute(delete(RecoveryCase).where(RecoveryCase.organization_id == org_id))
    session.execute(delete(WebhookEvent).where(WebhookEvent.organization_id == org_id))
    session.execute(delete(MerchantPolicy).where(MerchantPolicy.organization_id == org_id))
    session.execute(delete(Invoice).where(Invoice.organization_id == org_id))
    session.execute(delete(Subscription).where(Subscription.organization_id == org_id))
    session.execute(delete(Transaction).where(Transaction.organization_id == org_id))
    session.execute(delete(Customer).where(Customer.organization_id == org_id))
    session.execute(delete(UserProfile).where(UserProfile.organization_id == org_id))
    session.execute(delete(Organization).where(Organization.id == org_id))


def _persist_world(session: Session, spec: DemoSeedSpec) -> None:
    """Persist everything the recovery engine needs in order to analyse a case.

    Deliberately stops short of recommendations, actions, outcomes and audit
    history: those are produced from the real analysis, which cannot run until
    these rows exist. See `_persist_history`.
    """
    org = spec.organization
    session.add(
        Organization(
            id=org.id,
            name=org.name,
            currency=org.currency,
            automation_enabled=org.automation_enabled,
            created_at=org.created_at,
            updated_at=org.updated_at,
        )
    )

    for profile in spec.user_profiles:
        session.add(
            UserProfile(
                id=profile.id,
                organization_id=profile.organization_id,
                auth_user_id=profile.auth_user_id,
                role=profile.role,
                created_at=profile.created_at,
            )
        )

    for customer in spec.customers:
        session.add(
            Customer(
                id=customer.id,
                organization_id=customer.organization_id,
                external_id=customer.external_id,
                display_name=customer.display_name,
                email=customer.email,
                phone=customer.phone,
                segment=customer.segment,
                lifetime_value_minor=customer.lifetime_value_minor,
                is_synthetic=customer.is_synthetic,
                created_at=customer.created_at,
                updated_at=customer.updated_at,
            )
        )

    for txn in spec.transactions:
        session.add(
            Transaction(
                id=txn.id,
                organization_id=txn.organization_id,
                customer_id=txn.customer_id,
                provider=txn.provider,
                provider_payment_id=txn.provider_payment_id,
                provider_order_id=txn.provider_order_id,
                amount_minor=txn.amount_minor,
                currency=txn.currency,
                status=txn.status,
                payment_method=txn.payment_method,
                error_code=txn.error_code,
                error_reason=txn.error_reason,
                error_source=txn.error_source,
                error_step=txn.error_step,
                error_description=txn.error_description,
                provider_created_at=txn.provider_created_at,
                last_provider_event_at=txn.last_provider_event_at,
                metadata_=txn.metadata,
                is_synthetic=txn.is_synthetic,
                created_at=txn.created_at,
                updated_at=txn.updated_at,
            )
        )

    for sub in spec.subscriptions:
        session.add(
            Subscription(
                id=sub.id,
                organization_id=sub.organization_id,
                customer_id=sub.customer_id,
                provider=sub.provider,
                provider_subscription_id=sub.provider_subscription_id,
                amount_minor=sub.amount_minor,
                currency=sub.currency,
                status=sub.status,
                retry_count=sub.retry_count,
                current_period_end=sub.current_period_end,
                next_charge_at=sub.next_charge_at,
                last_provider_event_at=sub.last_provider_event_at,
                metadata_=sub.metadata,
                is_synthetic=sub.is_synthetic,
                created_at=sub.created_at,
                updated_at=sub.updated_at,
            )
        )

    for case in spec.recovery_cases:
        session.add(
            RecoveryCase(
                id=case.id,
                organization_id=case.organization_id,
                customer_id=case.customer_id,
                transaction_id=case.transaction_id,
                subscription_id=case.subscription_id,
                invoice_id=case.invoice_id,
                source_event_key=case.source_event_key,
                case_type=case.case_type,
                amount_at_risk_minor=case.amount_at_risk_minor,
                currency=case.currency,
                failure_category=case.failure_category,
                status=case.status,
                priority_score=case.priority_score,
                recovery_probability=case.recovery_probability,
                expected_recoverable_minor=case.expected_recoverable_minor,
                current_analysis_run_id=case.current_analysis_run_id,
                opened_at=case.opened_at,
                last_transition_at=case.last_transition_at,
                resolved_at=case.resolved_at,
                version=case.version,
                created_at=case.created_at,
                updated_at=case.updated_at,
            )
        )

    if spec.merchant_policy is not None:
        policy = spec.merchant_policy
        session.add(
            MerchantPolicy(
                id=policy.id,
                organization_id=policy.organization_id,
                auto_action_limit_minor=policy.auto_action_limit_minor,
                max_recovery_attempts=policy.max_recovery_attempts,
                max_contacts_per_24h=policy.max_contacts_per_24h,
                minimum_auto_confidence=policy.minimum_auto_confidence,
                cooldown_minutes=policy.cooldown_minutes,
                automation_enabled=policy.automation_enabled,
                allowed_action_types=policy.allowed_action_types,
                created_at=policy.created_at,
                updated_at=policy.updated_at,
            )
        )


def _persist_history(session: Session, spec: DemoSeedSpec) -> None:
    """Persist the analysis and everything derived from it."""
    for rec in spec.recommendations:
        session.add(
            RecoveryRecommendation(
                id=rec.id,
                organization_id=rec.organization_id,
                case_id=rec.case_id,
                analysis_run_id=rec.analysis_run_id,
                action_type=rec.action_type,
                rank=rec.rank,
                success_probability=rec.success_probability,
                expected_recovered_minor=rec.expected_recovered_minor,
                expected_value_minor=rec.expected_value_minor,
                erv_action_cost_minor=rec.erv_action_cost_minor,
                erv_fatigue_penalty_minor=rec.erv_fatigue_penalty_minor,
                erv_operational_risk_penalty_minor=rec.erv_operational_risk_penalty_minor,
                erv_delay_penalty_minor=rec.erv_delay_penalty_minor,
                confidence=rec.confidence,
                policy_eligible=rec.policy_eligible,
                requires_approval=rec.requires_approval,
                policy_reasons=rec.policy_reasons,
                factors=rec.factors,
                model_version=rec.model_version,
                feature_schema_version=rec.feature_schema_version,
                created_at=rec.created_at,
            )
        )

    for action in spec.actions:
        session.add(
            RecoveryAction(
                id=action.id,
                organization_id=action.organization_id,
                case_id=action.case_id,
                recommendation_id=action.recommendation_id,
                action_type=action.action_type,
                status=action.status,
                attempt_number=action.attempt_number,
                requires_approval=action.requires_approval,
                approved_by=action.approved_by,
                approved_at=action.approved_at,
                idempotency_key=action.idempotency_key,
                request_fingerprint=action.request_fingerprint,
                scheduled_for=action.scheduled_for,
                execution_started_at=action.execution_started_at,
                executed_at=action.executed_at,
                provider_reference=action.provider_reference,
                provider_status=action.provider_status,
                error_category=action.error_category,
                error_message=action.error_message,
                metadata_=action.metadata,
                created_at=action.created_at,
                updated_at=action.updated_at,
            )
        )

    for outcome in spec.outcomes:
        session.add(
            RecoveryOutcome(
                id=outcome.id,
                organization_id=outcome.organization_id,
                case_id=outcome.case_id,
                outcome=outcome.outcome,
                recovered_amount_minor=outcome.recovered_amount_minor,
                recovered_payment_id=outcome.recovered_payment_id,
                verification_source=outcome.verification_source,
                verified_event_id=outcome.verified_event_id,
                recovered_at=outcome.recovered_at,
                time_to_recovery_seconds=outcome.time_to_recovery_seconds,
                metadata_=outcome.metadata,
                created_at=outcome.created_at,
            )
        )

    for entry in spec.audit_logs:
        session.add(
            AuditLog(
                id=entry.id,
                organization_id=entry.organization_id,
                case_id=entry.case_id,
                actor_type=entry.actor_type,
                actor_id=entry.actor_id,
                event_type=entry.event_type,
                summary=entry.summary,
                evidence=entry.evidence,
                created_at=entry.created_at,
            )
        )



def _analysis_plan(spec: DemoSeedSpec) -> dict[UUID, tuple[UUID, datetime]]:
    """Which seeded cases get a real analysis, under which run id and clock."""
    return {
        case.id: (case.current_analysis_run_id, seed_analysis_timestamp(case))
        for case in spec.recovery_cases
        if case.current_analysis_run_id is not None
    }


def _real_recommendation_builder(
    analyses: dict[UUID, SeededAnalysis],
) -> Callable[[RecoveryCaseSpec, UUID, str | None, datetime], list[RecommendationSpec]]:
    """Adapt real engine output into the factory's recommendation rows.

    Every field is copied from the computation. Nothing is rounded, rescaled or
    smoothed on the way through: the probabilities, expected values and policy
    verdicts a reviewer sees on a seeded case are the ones the model and the
    policy engine produced.
    """

    def build(
        case: RecoveryCaseSpec,
        analysis_run_id: UUID,
        logical_key: str | None,
        created_at: datetime,
    ) -> list[RecommendationSpec]:
        analysis = analyses.get(case.id)
        if analysis is None:
            raise SeedAnalysisError(f"No real analysis was produced for case {case.id}.")
        return [
            RecommendationSpec(
                id=demo_uuid(
                    f"recommendation:{case.id}:{analysis_run_id}:{row.action_type}"
                ),
                organization_id=case.organization_id,
                case_id=case.id,
                analysis_run_id=analysis_run_id,
                action_type=row.action_type,
                rank=row.rank,
                success_probability=row.success_probability,
                expected_recovered_minor=row.expected_recovered_minor,
                expected_value_minor=row.expected_value_minor,
                erv_action_cost_minor=row.erv_action_cost_minor,
                erv_fatigue_penalty_minor=row.erv_fatigue_penalty_minor,
                erv_operational_risk_penalty_minor=row.erv_operational_risk_penalty_minor,
                erv_delay_penalty_minor=row.erv_delay_penalty_minor,
                confidence=row.confidence,
                policy_eligible=row.policy_eligible,
                requires_approval=row.requires_approval,
                policy_reasons=list(row.policy_reasons),
                factors=list(row.factors),
                model_version=row.model_version,
                feature_schema_version=row.feature_schema_version,
                created_at=created_at,
            )
            for row in analysis.computation.recommendation_rows
        ]

    return build


def _apply_case_analysis_summaries(
    session: Session,
    analyses: dict[UUID, SeededAnalysis],
) -> None:
    """Write each case's summary columns from its real analysis.

    `recovery_probability`, `expected_recoverable_minor` and `priority_score`
    describe the action the engine selected. The factory cannot know them --
    it builds the case row before any analysis exists -- so it writes
    placeholders that this pass replaces.
    """
    for case_id, analysis in analyses.items():
        update = analysis.computation.case_update
        case = session.get(RecoveryCase, case_id)
        if case is None:  # pragma: no cover - defensive
            raise SeedAnalysisError(f"Case {case_id} vanished between passes.")
        case.current_analysis_run_id = update.current_analysis_run_id
        case.priority_score = update.priority_score
        case.recovery_probability = update.recovery_probability
        case.expected_recoverable_minor = update.expected_recoverable_minor


def seed_demo_database(*, reset: bool = False, settings: Settings | None = None) -> SeedResult:
    resolved = settings or get_settings()
    if reset:
        assert_reset_allowed(resolved)

    session_factory = get_session_factory(resolved)
    engine = _build_engine(resolved.database_url)
    assert_schema_ready(engine)

    with session_factory() as session:
        try:
            preserved: list[PreservedUserProfile] = []
            if reset:
                if demo_organization_exists(session):
                    # Capture before the delete: the rows are gone afterwards.
                    preserved = capture_external_user_profiles(session)
                    delete_demo_tenant(session)
                    session.flush()
            elif demo_organization_exists(session):
                session.rollback()
                return SeedResult(
                    created=False,
                    already_exists=True,
                    reset_performed=False,
                    organization_id=str(DEMO_ORGANIZATION_ID),
                )

            # Pass 1: lay down the world the engine reads from. The factory is
            # pure and deterministic, so running it twice costs nothing.
            world = build_demo_seed_spec()
            _persist_world(session, world)
            session.flush()

            # Pass 2: analyse the persisted cases with the production engine,
            # then rebuild the spec so that recommendations -- and the actions,
            # outcomes and audit entries derived from them -- come from what the
            # engine actually selected, not from a canned table.
            analyses = analyse_seeded_cases(
                session,
                settings=resolved,
                organization_id=DEMO_ORGANIZATION_ID,
                analysis_plan=_analysis_plan(world),
            )
            spec = build_demo_seed_spec(
                recommendations_for_case=_real_recommendation_builder(analyses)
            )
            _persist_history(session, spec)
            session.flush()

            # The case summary columns describe the SELECTED action, so they
            # have to be rewritten from the real analysis rather than left at
            # the factory's placeholder.
            _apply_case_analysis_summaries(session, analyses)
            session.flush()
            # After the reseed, so the organization row these profiles
            # reference exists again.
            restored = restore_external_user_profiles(session, preserved)
            session.flush()
            session.commit()
        except Exception:
            session.rollback()
            raise

    return SeedResult(
        created=True,
        already_exists=False,
        reset_performed=reset,
        organization_id=str(DEMO_ORGANIZATION_ID),
        preserved_user_profiles=restored,
    )
