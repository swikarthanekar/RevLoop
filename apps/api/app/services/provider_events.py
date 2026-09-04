"""Provider webhook event orchestration (Prompt 14)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.enums import (
    AuditActorType,
    CaseType,
    FailureCategory,
    RecoveryActionStatus,
    RecoveryActionType,
    RecoveryCaseStatus,
    RecoveryOutcomeType,
    VerificationSource,
    WebhookProcessingStatus,
)
from app.integrations.razorpay.errors import (
    MalformedWebhookPayloadError,
    WebhookConfigurationError,
    WebhookCorrelationError,
    WebhookProcessingError,
)
from app.integrations.razorpay.schemas import (
    RazorpayPaymentEntity,
    RazorpaySubscriptionEntity,
    RazorpayWebhookEnvelope,
)
from app.models.customer import Customer
from app.models.recovery_action import RecoveryAction
from app.models.recovery_case import RecoveryCase
from app.models.recovery_outcome import RecoveryOutcome
from app.models.subscription import Subscription
from app.models.transaction import Transaction
from app.models.webhook_event import WebhookEvent
from app.repositories.audit_logs import AuditLogWorkflowRepository
from app.repositories.webhook_events import PROVIDER_RAZORPAY, WebhookEventRepository
from app.workflows.exceptions import TerminalStateError, WorkflowError
from app.workflows.schemas import TransitionContext
from app.workflows.state_machine import RecoveryCaseStateMachine

logger = logging.getLogger(__name__)

PAYMENT_TERMINAL_SUCCESS = "captured"
PAYMENT_FAILED = "failed"
SUBSCRIPTION_CHARGED = "active"
SUBSCRIPTION_PENDING = "pending"
SUBSCRIPTION_HALTED = "halted"

STALE_REASON = "STALE_WEBHOOK_IGNORED"
UNCORRELATED_PAYMENT_LINK = "UNCORRELATED_PAYMENT_LINK"
UNKNOWN_EVENT = "UNSUPPORTED_EVENT_TYPE"
INSUFFICIENT_FINANCIAL_EVIDENCE = "INSUFFICIENT_FINANCIAL_EVIDENCE"
MONEY_MISMATCH = "RECOVERY_MONEY_MISMATCH"
INSUFFICIENT_PAYMENT_EVIDENCE = "INSUFFICIENT_PAYMENT_EVIDENCE"
TERMINAL_STATE_RECONCILIATION_REQUIRED = "TERMINAL_STATE_RECONCILIATION_REQUIRED"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def resolve_webhook_organization_id(settings: Settings) -> UUID:
    """Map verified webhook to configured tenant (P0 single-account deployment)."""
    organization_id = settings.dev_auth_organization_id
    if organization_id is None:
        raise WebhookConfigurationError("Webhook organization is not configured.")
    return organization_id


def payment_failed_source_event_key(payment_id: str) -> str:
    return f"razorpay:payment_failed:{payment_id}"


def subscription_pending_source_event_key(subscription_id: str, cycle_key: str) -> str:
    return f"razorpay:subscription_pending:{subscription_id}:{cycle_key}"


def subscription_billing_cycle_key(entity: RazorpaySubscriptionEntity) -> str:
    if entity.current_start is not None and entity.current_end is not None:
        return f"{entity.current_start}:{entity.current_end}"
    if entity.current_start is not None:
        return str(entity.current_start)
    if entity.current_end is not None:
        return str(entity.current_end)
    return "unknown"


def require_provider_event_timestamp(envelope: RazorpayWebhookEnvelope) -> datetime:
    """Return authoritative provider event time; never substitute receipt time."""
    if envelope.provider_created_at is None:
        raise MalformedWebhookPayloadError("Webhook envelope missing created_at.")
    return envelope.provider_created_at


def _payment_status_rank(status: str) -> int:
    ranks = {
        "created": 1,
        "authorized": 2,
        "failed": 3,
        "captured": 4,
    }
    return ranks.get(status, 0)


def _should_apply_payment_state(
    *,
    current_status: str,
    current_event_at: datetime | None,
    new_status: str,
    new_event_at: datetime | None,
) -> bool:
    if current_status == PAYMENT_TERMINAL_SUCCESS and new_status == PAYMENT_FAILED:
        return False
    if new_status == PAYMENT_TERMINAL_SUCCESS:
        return True
    if current_event_at and new_event_at and new_event_at < current_event_at:
        return False
    if _payment_status_rank(new_status) < _payment_status_rank(current_status):
        return False
    return True


def _should_apply_subscription_state(
    *,
    current_status: str,
    current_event_at: datetime | None,
    new_status: str,
    new_event_at: datetime | None,
    event_type: str,
) -> bool:
    # Ordering is checked first, even for `subscription.charged`: Razorpay does
    # not guarantee webhook delivery order, so a charged event for an older
    # cycle can arrive after a newer halted/pending event. Treating charged as
    # unconditionally authoritative would revert the subscription status and
    # then cause the *next genuinely newer* event to be rejected as stale
    # (see the current_status == SUBSCRIPTION_CHARGED rule below).
    if current_event_at and new_event_at and new_event_at < current_event_at:
        return False
    if event_type == "subscription.charged":
        return True
    if current_status == SUBSCRIPTION_CHARGED and event_type == "subscription.pending":
        return False
    return True


def _validate_recovery_money(
    *,
    case: RecoveryCase,
    recovered_amount_minor: int,
    currency: str,
) -> bool:
    return (
        case.amount_at_risk_minor == recovered_amount_minor
        and case.currency == currency.strip().upper()
    )


class ProviderEventService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        webhook_repo: WebhookEventRepository | None = None,
        state_machine: RecoveryCaseStateMachine | None = None,
        audit_repo: AuditLogWorkflowRepository | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._webhook_repo = webhook_repo or WebhookEventRepository()
        self._state_machine = state_machine or RecoveryCaseStateMachine()
        self._audit_repo = audit_repo or AuditLogWorkflowRepository()

    def ingest_razorpay_webhook(
        self,
        *,
        raw_body: bytes,
        provider_event_id: str,
        settings: Settings,
    ) -> tuple[WebhookEvent, bool]:
        """Parse verified payload, claim idempotently, and process when needed."""
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MalformedWebhookPayloadError("Webhook body is not valid JSON.") from exc

        if not isinstance(payload, dict):
            raise MalformedWebhookPayloadError("Webhook body must be a JSON object.")

        try:
            envelope = RazorpayWebhookEnvelope.model_validate(payload)
        except Exception as exc:
            raise MalformedWebhookPayloadError("Webhook payload failed validation.") from exc

        organization_id = resolve_webhook_organization_id(settings)
        received_at = _utcnow()
        event, claim_status = self._webhook_repo.claim_event(
            self._session,
            organization_id=organization_id,
            provider=PROVIDER_RAZORPAY,
            provider_event_id=provider_event_id,
            event_type=envelope.event,
            provider_created_at=envelope.provider_created_at,
            payload=payload,
            received_at=received_at,
        )
        if claim_status == "complete":
            return event, False

        try:
            self._process_envelope(
                envelope=envelope,
                webhook_event=event,
                organization_id=organization_id,
            )
            if event.processing_status in {
                WebhookProcessingStatus.RECEIVED.value,
                WebhookProcessingStatus.FAILED.value,
            }:
                self._webhook_repo.mark_processed(
                    self._session, event=event, processed_at=_utcnow()
                )
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise

        return event, True

    def _process_envelope(
        self,
        *,
        envelope: RazorpayWebhookEnvelope,
        webhook_event: WebhookEvent,
        organization_id: UUID,
    ) -> None:
        handlers = {
            "payment.failed": self._handle_payment_failed,
            "payment.captured": self._handle_payment_captured,
            "subscription.pending": self._handle_subscription_pending,
            "subscription.charged": self._handle_subscription_charged,
            "subscription.halted": self._handle_subscription_halted,
            "payment_link.paid": self._handle_payment_link_paid,
        }
        handler = handlers.get(envelope.event)
        if handler is None:
            self._webhook_repo.mark_ignored(
                self._session,
                event=webhook_event,
                processed_at=_utcnow(),
                reason=UNKNOWN_EVENT,
            )
            return
        handler(
            envelope=envelope,
            webhook_event=webhook_event,
            organization_id=organization_id,
        )

    def _resolve_customer_for_payment(
        self,
        *,
        organization_id: UUID,
        payment: RazorpayPaymentEntity,
    ) -> Customer:
        notes = payment.notes or {}
        external_id = notes.get("revloop_customer") or notes.get("customer_external_id")
        if external_id:
            customer = self._session.execute(
                select(Customer).where(
                    Customer.organization_id == organization_id,
                    Customer.external_id == str(external_id),
                )
            ).scalar_one_or_none()
            if customer is not None:
                return customer

        if payment.email:
            customer = self._session.execute(
                select(Customer).where(
                    Customer.organization_id == organization_id,
                    Customer.email == payment.email,
                )
            ).scalar_one_or_none()
            if customer is not None:
                return customer

        raise WebhookCorrelationError(
            f"Unable to correlate customer for payment {payment.id}."
        )

    def _resolve_customer_for_subscription(
        self,
        *,
        organization_id: UUID,
        subscription: RazorpaySubscriptionEntity,
    ) -> Customer:
        notes = subscription.notes or {}
        external_id = notes.get("revloop_customer") or notes.get("customer_external_id")
        if external_id:
            customer = self._session.execute(
                select(Customer).where(
                    Customer.organization_id == organization_id,
                    Customer.external_id == str(external_id),
                )
            ).scalar_one_or_none()
            if customer is not None:
                return customer
        raise WebhookCorrelationError(
            f"Unable to correlate customer for subscription {subscription.id}."
        )

    def _get_transaction_by_payment_id(
        self,
        *,
        organization_id: UUID,
        payment_id: str,
    ) -> Transaction | None:
        return self._session.execute(
            select(Transaction).where(
                Transaction.organization_id == organization_id,
                Transaction.provider == PROVIDER_RAZORPAY,
                Transaction.provider_payment_id == payment_id,
            )
        ).scalar_one_or_none()

    def _get_subscription_by_provider_id(
        self,
        *,
        organization_id: UUID,
        subscription_id: str,
    ) -> Subscription | None:
        return self._session.execute(
            select(Subscription).where(
                Subscription.organization_id == organization_id,
                Subscription.provider == PROVIDER_RAZORPAY,
                Subscription.provider_subscription_id == subscription_id,
            )
        ).scalar_one_or_none()

    def _upsert_transaction_from_payment(
        self,
        *,
        organization_id: UUID,
        payment: RazorpayPaymentEntity,
        event_at: datetime,
        force_status: str | None = None,
    ) -> tuple[Transaction, bool]:
        existing = self._get_transaction_by_payment_id(
            organization_id=organization_id,
            payment_id=payment.id,
        )
        new_status = force_status or payment.status
        if existing is not None:
            if not _should_apply_payment_state(
                current_status=existing.status,
                current_event_at=existing.last_provider_event_at,
                new_status=new_status,
                new_event_at=event_at,
            ):
                return existing, False
            existing.status = new_status
            existing.amount_minor = payment.amount
            existing.currency = payment.currency
            existing.payment_method = payment.method
            existing.error_code = payment.error_code
            existing.error_reason = payment.error_reason
            existing.error_source = payment.error_source
            existing.error_step = payment.error_step
            existing.error_description = payment.error_description
            existing.last_provider_event_at = event_at
            self._session.flush()
            return existing, True

        customer = self._resolve_customer_for_payment(
            organization_id=organization_id,
            payment=payment,
        )
        transaction = Transaction(
            organization_id=organization_id,
            customer_id=customer.id,
            provider=PROVIDER_RAZORPAY,
            provider_payment_id=payment.id,
            provider_order_id=payment.order_id,
            amount_minor=payment.amount,
            currency=payment.currency,
            status=new_status,
            payment_method=payment.method,
            error_code=payment.error_code,
            error_reason=payment.error_reason,
            error_source=payment.error_source,
            error_step=payment.error_step,
            error_description=payment.error_description,
            provider_created_at=payment.provider_created_at,
            last_provider_event_at=event_at,
            is_synthetic=False,
        )
        self._session.add(transaction)
        self._session.flush()
        return transaction, True

    def _upsert_subscription(
        self,
        *,
        organization_id: UUID,
        subscription_entity: RazorpaySubscriptionEntity,
        event_at: datetime,
        event_type: str,
        status_override: str | None = None,
    ) -> tuple[Subscription | None, bool]:
        existing = self._get_subscription_by_provider_id(
            organization_id=organization_id,
            subscription_id=subscription_entity.id,
        )
        new_status = status_override or subscription_entity.status
        if existing is not None:
            if not _should_apply_subscription_state(
                current_status=existing.status,
                current_event_at=existing.last_provider_event_at,
                new_status=new_status,
                new_event_at=event_at,
                event_type=event_type,
            ):
                return existing, False
            existing.status = new_status
            existing.last_provider_event_at = event_at
            self._session.flush()
            return existing, True

        raise WebhookCorrelationError(
            f"No trusted local subscription record for {subscription_entity.id}."
        )

    def _create_payment_failure_case_if_absent(
        self,
        *,
        organization_id: UUID,
        transaction: Transaction,
        payment_id: str,
        opened_at: datetime,
    ) -> RecoveryCase | None:
        source_event_key = payment_failed_source_event_key(payment_id)
        existing = self._session.execute(
            select(RecoveryCase).where(
                RecoveryCase.organization_id == organization_id,
                RecoveryCase.source_event_key == source_event_key,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        now = _utcnow()
        case = RecoveryCase(
            organization_id=organization_id,
            customer_id=transaction.customer_id,
            transaction_id=transaction.id,
            source_event_key=source_event_key,
            case_type=CaseType.PAYMENT_FAILURE.value,
            amount_at_risk_minor=transaction.amount_minor,
            currency=transaction.currency,
            failure_category=FailureCategory.UNKNOWN.value,
            status=RecoveryCaseStatus.DETECTED.value,
            opened_at=opened_at,
            last_transition_at=now,
            version=1,
        )
        self._session.add(case)
        try:
            with self._session.begin_nested():
                self._session.flush()
        except IntegrityError:
            return self._session.execute(
                select(RecoveryCase).where(
                    RecoveryCase.organization_id == organization_id,
                    RecoveryCase.source_event_key == source_event_key,
                )
            ).scalar_one()
        self._audit_repo.insert_transition_audit(
            self._session,
            organization_id=organization_id,
            case_id=case.id,
            actor_type=AuditActorType.PROVIDER,
            actor_id=PROVIDER_RAZORPAY,
            event_type="CASE_CREATED",
            summary="Recovery case created from payment.failed webhook.",
            evidence={"source_event_key": source_event_key, "payment_id": payment_id},
        )
        return case

    def _create_subscription_failure_case_if_absent(
        self,
        *,
        organization_id: UUID,
        subscription: Subscription,
        source_event_key: str,
        opened_at: datetime,
    ) -> RecoveryCase | None:
        existing = self._session.execute(
            select(RecoveryCase).where(
                RecoveryCase.organization_id == organization_id,
                RecoveryCase.source_event_key == source_event_key,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        now = _utcnow()
        case = RecoveryCase(
            organization_id=organization_id,
            customer_id=subscription.customer_id,
            subscription_id=subscription.id,
            source_event_key=source_event_key,
            case_type=CaseType.SUBSCRIPTION_FAILURE.value,
            amount_at_risk_minor=subscription.amount_minor,
            currency=subscription.currency,
            failure_category=FailureCategory.MANDATE_OR_RECURRING_FAILURE.value,
            status=RecoveryCaseStatus.DETECTED.value,
            opened_at=opened_at,
            last_transition_at=now,
            version=1,
        )
        self._session.add(case)
        try:
            with self._session.begin_nested():
                self._session.flush()
        except IntegrityError:
            return self._session.execute(
                select(RecoveryCase).where(
                    RecoveryCase.organization_id == organization_id,
                    RecoveryCase.source_event_key == source_event_key,
                )
            ).scalar_one()
        self._audit_repo.insert_transition_audit(
            self._session,
            organization_id=organization_id,
            case_id=case.id,
            actor_type=AuditActorType.PROVIDER,
            actor_id=PROVIDER_RAZORPAY,
            event_type="CASE_CREATED",
            summary="Recovery case created from subscription.pending webhook.",
            evidence={"source_event_key": source_event_key},
        )
        return case

    def _find_case_by_source_event_key(
        self,
        *,
        organization_id: UUID,
        source_event_key: str,
    ) -> RecoveryCase | None:
        return self._session.execute(
            select(RecoveryCase).where(
                RecoveryCase.organization_id == organization_id,
                RecoveryCase.source_event_key == source_event_key,
            )
        ).scalar_one_or_none()

    def _find_case_for_transaction(
        self,
        *,
        organization_id: UUID,
        transaction_id: UUID,
    ) -> RecoveryCase | None:
        return self._session.execute(
            select(RecoveryCase)
            .where(
                RecoveryCase.organization_id == organization_id,
                RecoveryCase.transaction_id == transaction_id,
            )
            .order_by(RecoveryCase.opened_at.desc())
        ).scalars().first()

    def _find_open_case_for_transaction(
        self,
        *,
        organization_id: UUID,
        transaction_id: UUID,
    ) -> RecoveryCase | None:
        terminal = {
            RecoveryCaseStatus.RECOVERED.value,
            RecoveryCaseStatus.FAILED.value,
            RecoveryCaseStatus.STOPPED.value,
        }
        return self._session.execute(
            select(RecoveryCase)
            .where(
                RecoveryCase.organization_id == organization_id,
                RecoveryCase.transaction_id == transaction_id,
                RecoveryCase.status.notin_(terminal),
            )
            .order_by(RecoveryCase.opened_at.desc())
        ).scalars().first()

    def _find_payment_link_action(
        self,
        *,
        organization_id: UUID,
        provider_reference: str,
    ) -> RecoveryAction | None:
        return self._session.execute(
            select(RecoveryAction).where(
                RecoveryAction.organization_id == organization_id,
                RecoveryAction.provider_reference == provider_reference,
                RecoveryAction.action_type == RecoveryActionType.CREATE_PAYMENT_LINK.value,
            )
        ).scalar_one_or_none()

    def _record_terminal_reconciliation_required(
        self,
        *,
        case: RecoveryCase,
        webhook_event: WebhookEvent,
        organization_id: UUID,
    ) -> None:
        logger.warning(
            "Verified success contradicts terminal case %s in status %s",
            case.id,
            case.status,
        )
        self._webhook_repo.mark_ignored(
            self._session,
            event=webhook_event,
            processed_at=_utcnow(),
            reason=TERMINAL_STATE_RECONCILIATION_REQUIRED,
        )
        self._audit_repo.insert_transition_audit(
            self._session,
            organization_id=organization_id,
            case_id=case.id,
            actor_type=AuditActorType.PROVIDER,
            actor_id=PROVIDER_RAZORPAY,
            event_type="TERMINAL_RECONCILIATION_REQUIRED",
            summary="Verified provider success contradicts terminal recovery case.",
            evidence={
                "case_status": case.status,
                "webhook_event_id": str(webhook_event.id),
            },
        )

    def _resolve_case_success(
        self,
        *,
        case: RecoveryCase,
        webhook_event: WebhookEvent,
        organization_id: UUID,
        recovered_amount_minor: int,
        currency: str,
        recovered_payment_id: str | None,
        recovered_at: datetime,
    ) -> None:
        terminal_status = RecoveryCaseStatus(case.status)
        if terminal_status == RecoveryCaseStatus.RECOVERED:
            return

        if terminal_status in {
            RecoveryCaseStatus.FAILED,
            RecoveryCaseStatus.STOPPED,
        }:
            if not _validate_recovery_money(
                case=case,
                recovered_amount_minor=recovered_amount_minor,
                currency=currency,
            ):
                self._webhook_repo.mark_ignored(
                    self._session,
                    event=webhook_event,
                    processed_at=_utcnow(),
                    reason=MONEY_MISMATCH,
                )
                return
            self._record_terminal_reconciliation_required(
                case=case,
                webhook_event=webhook_event,
                organization_id=organization_id,
            )
            return

        if not _validate_recovery_money(
            case=case,
            recovered_amount_minor=recovered_amount_minor,
            currency=currency,
        ):
            self._webhook_repo.mark_ignored(
                self._session,
                event=webhook_event,
                processed_at=_utcnow(),
                reason=MONEY_MISMATCH,
            )
            return

        savepoint = self._session.begin_nested()
        try:
            self._create_outcome_if_absent(
                organization_id=organization_id,
                case=case,
                webhook_event=webhook_event,
                recovered_amount_minor=recovered_amount_minor,
                recovered_payment_id=recovered_payment_id,
                recovered_at=recovered_at,
            )
            self._cancel_pending_actions(organization_id=organization_id, case_id=case.id)

            context = TransitionContext(
                organization_id=organization_id,
                actor_type=AuditActorType.PROVIDER,
                actor_id=PROVIDER_RAZORPAY,
                reason="PAYMENT_VERIFIED",
                metadata={"webhook_event_id": str(webhook_event.id)},
                occurred_at=recovered_at,
            )
            self._state_machine.resolve_verified_success(
                self._session,
                case_id=case.id,
                organization_id=organization_id,
                expected_version=case.version,
                context=context,
            )
        except TerminalStateError:
            savepoint.rollback()
            return
        except WorkflowError as exc:
            savepoint.rollback()
            raise WebhookProcessingError(
                f"PAYMENT_VERIFIED failed for case {case.id}: {exc}"
            ) from exc

    def _create_outcome_if_absent(
        self,
        *,
        organization_id: UUID,
        case: RecoveryCase,
        webhook_event: WebhookEvent,
        recovered_amount_minor: int,
        recovered_payment_id: str | None,
        recovered_at: datetime,
    ) -> RecoveryOutcome:
        existing = self._session.execute(
            select(RecoveryOutcome).where(
                RecoveryOutcome.case_id == case.id,
                RecoveryOutcome.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        outcome = RecoveryOutcome(
            organization_id=organization_id,
            case_id=case.id,
            outcome=RecoveryOutcomeType.RECOVERED.value,
            recovered_amount_minor=recovered_amount_minor,
            recovered_payment_id=recovered_payment_id,
            verification_source=VerificationSource.WEBHOOK.value,
            verified_event_id=webhook_event.id,
            recovered_at=recovered_at,
            time_to_recovery_seconds=max(
                0,
                int((recovered_at - case.opened_at).total_seconds()),
            ),
        )
        self._session.add(outcome)
        self._session.flush()
        return outcome

    def _cancel_pending_actions(self, *, organization_id: UUID, case_id: UUID) -> None:
        now = _utcnow()
        self._session.execute(
            update(RecoveryAction)
            .where(
                RecoveryAction.organization_id == organization_id,
                RecoveryAction.case_id == case_id,
                RecoveryAction.status.in_(
                    [
                        RecoveryActionStatus.PENDING_APPROVAL.value,
                        RecoveryActionStatus.SCHEDULED.value,
                    ]
                ),
            )
            .values(status=RecoveryActionStatus.CANCELLED.value, updated_at=now)
        )

    def _handle_payment_failed(
        self,
        *,
        envelope: RazorpayWebhookEnvelope,
        webhook_event: WebhookEvent,
        organization_id: UUID,
    ) -> None:
        payment = envelope.payment_entity()
        if payment is None:
            raise MalformedWebhookPayloadError("payment.failed missing payment entity.")

        event_at = require_provider_event_timestamp(envelope)
        try:
            transaction, applied = self._upsert_transaction_from_payment(
                organization_id=organization_id,
                payment=payment,
                event_at=event_at,
                force_status=PAYMENT_FAILED,
            )
        except WebhookCorrelationError:
            self._webhook_repo.mark_ignored(
                self._session,
                event=webhook_event,
                processed_at=_utcnow(),
                reason=INSUFFICIENT_FINANCIAL_EVIDENCE,
            )
            return
        if not applied or transaction.status == PAYMENT_TERMINAL_SUCCESS:
            self._webhook_repo.mark_ignored(
                self._session,
                event=webhook_event,
                processed_at=_utcnow(),
                reason=STALE_REASON,
            )
            return

        self._create_payment_failure_case_if_absent(
            organization_id=organization_id,
            transaction=transaction,
            payment_id=payment.id,
            opened_at=event_at,
        )

    def _handle_payment_captured(
        self,
        *,
        envelope: RazorpayWebhookEnvelope,
        webhook_event: WebhookEvent,
        organization_id: UUID,
    ) -> None:
        payment = envelope.payment_entity()
        if payment is None:
            raise MalformedWebhookPayloadError("payment.captured missing payment entity.")

        event_at = require_provider_event_timestamp(envelope)
        try:
            transaction, _applied = self._upsert_transaction_from_payment(
                organization_id=organization_id,
                payment=payment,
                event_at=event_at,
                force_status=PAYMENT_TERMINAL_SUCCESS,
            )
        except WebhookCorrelationError:
            self._webhook_repo.mark_ignored(
                self._session,
                event=webhook_event,
                processed_at=_utcnow(),
                reason=INSUFFICIENT_FINANCIAL_EVIDENCE,
            )
            return

        case = self._find_case_for_transaction(
            organization_id=organization_id,
            transaction_id=transaction.id,
        )
        if case is None:
            return

        self._resolve_case_success(
            case=case,
            webhook_event=webhook_event,
            organization_id=organization_id,
            recovered_amount_minor=payment.amount,
            currency=payment.currency,
            recovered_payment_id=payment.id,
            recovered_at=event_at,
        )

    def _handle_subscription_pending(
        self,
        *,
        envelope: RazorpayWebhookEnvelope,
        webhook_event: WebhookEvent,
        organization_id: UUID,
    ) -> None:
        subscription_entity = envelope.subscription_entity()
        if subscription_entity is None:
            raise MalformedWebhookPayloadError("subscription.pending missing subscription entity.")

        event_at = require_provider_event_timestamp(envelope)
        try:
            subscription, applied = self._upsert_subscription(
                organization_id=organization_id,
                subscription_entity=subscription_entity,
                event_at=event_at,
                event_type=envelope.event,
                status_override=SUBSCRIPTION_PENDING,
            )
        except WebhookCorrelationError:
            self._webhook_repo.mark_ignored(
                self._session,
                event=webhook_event,
                processed_at=_utcnow(),
                reason=INSUFFICIENT_FINANCIAL_EVIDENCE,
            )
            return

        if subscription is None or not applied:
            self._webhook_repo.mark_ignored(
                self._session,
                event=webhook_event,
                processed_at=_utcnow(),
                reason=STALE_REASON,
            )
            return

        cycle_key = subscription_billing_cycle_key(subscription_entity)
        source_event_key = subscription_pending_source_event_key(
            subscription_entity.id,
            cycle_key,
        )
        self._create_subscription_failure_case_if_absent(
            organization_id=organization_id,
            subscription=subscription,
            source_event_key=source_event_key,
            opened_at=event_at,
        )

    def _handle_subscription_charged(
        self,
        *,
        envelope: RazorpayWebhookEnvelope,
        webhook_event: WebhookEvent,
        organization_id: UUID,
    ) -> None:
        subscription_entity = envelope.subscription_entity()
        if subscription_entity is None:
            raise MalformedWebhookPayloadError("subscription.charged missing subscription entity.")

        payment = envelope.payment_entity()
        if payment is None:
            raise MalformedWebhookPayloadError("subscription.charged missing payment entity.")

        if payment.status != PAYMENT_TERMINAL_SUCCESS:
            self._webhook_repo.mark_ignored(
                self._session,
                event=webhook_event,
                processed_at=_utcnow(),
                reason=INSUFFICIENT_PAYMENT_EVIDENCE,
            )
            return

        event_at = require_provider_event_timestamp(envelope)
        try:
            subscription, _applied = self._upsert_subscription(
                organization_id=organization_id,
                subscription_entity=subscription_entity,
                event_at=event_at,
                event_type=envelope.event,
                status_override=SUBSCRIPTION_CHARGED,
            )
        except WebhookCorrelationError:
            return

        if subscription is None:
            return

        cycle_key = subscription_billing_cycle_key(subscription_entity)
        source_event_key = subscription_pending_source_event_key(
            subscription_entity.id,
            cycle_key,
        )
        case = self._find_case_by_source_event_key(
            organization_id=organization_id,
            source_event_key=source_event_key,
        )
        if case is None:
            return

        self._resolve_case_success(
            case=case,
            webhook_event=webhook_event,
            organization_id=organization_id,
            recovered_amount_minor=payment.amount,
            currency=payment.currency,
            recovered_payment_id=payment.id,
            recovered_at=event_at,
        )

    def _handle_subscription_halted(
        self,
        *,
        envelope: RazorpayWebhookEnvelope,
        webhook_event: WebhookEvent,
        organization_id: UUID,
    ) -> None:
        subscription_entity = envelope.subscription_entity()
        if subscription_entity is None:
            raise MalformedWebhookPayloadError("subscription.halted missing subscription entity.")

        event_at = require_provider_event_timestamp(envelope)
        try:
            self._upsert_subscription(
                organization_id=organization_id,
                subscription_entity=subscription_entity,
                event_at=event_at,
                event_type=envelope.event,
                status_override=SUBSCRIPTION_HALTED,
            )
        except WebhookCorrelationError:
            self._webhook_repo.mark_ignored(
                self._session,
                event=webhook_event,
                processed_at=_utcnow(),
                reason=INSUFFICIENT_FINANCIAL_EVIDENCE,
            )

    def _handle_payment_link_paid(
        self,
        *,
        envelope: RazorpayWebhookEnvelope,
        webhook_event: WebhookEvent,
        organization_id: UUID,
    ) -> None:
        payment_link = envelope.payment_link_entity()
        if payment_link is None:
            raise MalformedWebhookPayloadError("payment_link.paid missing payment_link entity.")

        payment = envelope.payment_entity()
        if payment is None:
            raise MalformedWebhookPayloadError(
                "payment_link.paid missing payment entity."
            )

        reference = payment_link.reference_id
        if not reference:
            self._webhook_repo.mark_ignored(
                self._session,
                event=webhook_event,
                processed_at=_utcnow(),
                reason=UNCORRELATED_PAYMENT_LINK,
            )
            return

        action = self._find_payment_link_action(
            organization_id=organization_id,
            provider_reference=reference,
        )
        if action is None:
            self._webhook_repo.mark_ignored(
                self._session,
                event=webhook_event,
                processed_at=_utcnow(),
                reason=UNCORRELATED_PAYMENT_LINK,
            )
            return

        case = self._session.execute(
            select(RecoveryCase).where(
                RecoveryCase.id == action.case_id,
                RecoveryCase.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if case is None:
            self._webhook_repo.mark_ignored(
                self._session,
                event=webhook_event,
                processed_at=_utcnow(),
                reason=UNCORRELATED_PAYMENT_LINK,
            )
            return

        event_at = require_provider_event_timestamp(envelope)
        self._resolve_case_success(
            case=case,
            webhook_event=webhook_event,
            organization_id=organization_id,
            recovered_amount_minor=payment.amount,
            currency=payment.currency,
            recovered_payment_id=payment.id,
            recovered_at=event_at,
        )
