"""Persist deterministic demo seed data and perform tenant-scoped reset."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import _build_engine, get_session_factory
from app.demo.constants import DEMO_ORGANIZATION_ID
from app.demo.factory import DemoSeedSpec, build_demo_seed_spec
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


class ResetNotAllowedError(SeedError):
    pass


@dataclass(frozen=True)
class SeedResult:
    created: bool
    already_exists: bool
    reset_performed: bool
    organization_id: str


def assert_schema_ready(engine: Engine) -> None:
    table_names = set(inspect(engine).get_table_names())
    missing = sorted(REQUIRED_TABLES - table_names)
    if missing:
        raise SeedError(
            "Database schema is not ready. Run: alembic upgrade head. "
            f"Missing tables: {', '.join(missing)}"
        )


def assert_reset_allowed(settings: Settings) -> None:
    if settings.is_production:
        raise ResetNotAllowedError("Reset refused: APP_ENV=production")
    if not settings.demo_mode:
        raise ResetNotAllowedError("Reset refused: DEMO_MODE is not enabled")


def demo_organization_exists(session: Session) -> bool:
    return (
        session.execute(
            select(Organization.id).where(Organization.id == DEMO_ORGANIZATION_ID)
        ).scalar_one_or_none()
        is not None
    )


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


def _persist_spec(session: Session, spec: DemoSeedSpec) -> None:
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


def seed_demo_database(*, reset: bool = False, settings: Settings | None = None) -> SeedResult:
    resolved = settings or get_settings()
    if reset:
        assert_reset_allowed(resolved)

    session_factory = get_session_factory(resolved)
    engine = _build_engine(resolved.database_url)
    assert_schema_ready(engine)

    with session_factory() as session:
        try:
            if reset:
                if demo_organization_exists(session):
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

            spec = build_demo_seed_spec()
            _persist_spec(session, spec)
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
    )
