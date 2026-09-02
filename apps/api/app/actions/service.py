"""Recovery action orchestration service (Prompt 16)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.actions.exceptions import (
    ActionBlockedByPolicyError,
    ActionConflictError,
    ActionNotFoundError,
    CaseNotActionableError,
    StaleRecommendationError,
    UnsupportedActionError,
)
from app.actions.keys import (
    build_action_idempotency_key,
    build_payment_link_reference_id,
    build_request_fingerprint,
)
from app.actions.repository import RecoveryActionRepository
from app.core.config import Settings
from app.domain.enums import (
    AuditActorType,
    RecoveryActionStatus,
    RecoveryActionType,
    RecoveryCaseStatus,
)
from app.integrations.razorpay.client import RazorpayClient
from app.integrations.razorpay.errors import (
    PaymentLinkSideEffectUnknownError,
    RazorpayApiError,
    RazorpayAuthenticationError,
    RazorpayRateLimitError,
    RazorpayTimeoutUnknownResult,
    RazorpayTransientError,
    RazorpayValidationError,
)
from app.integrations.razorpay.payment_links import (
    create_payment_link,
    fetch_payment_links_by_reference,
)
from app.integrations.razorpay.provider import acquire_razorpay_read_client
from app.models.customer import Customer
from app.models.merchant_policy import MerchantPolicy
from app.models.recovery_action import RecoveryAction
from app.models.recovery_case import RecoveryCase
from app.models.recovery_recommendation import RecoveryRecommendation
from app.policies.engine import evaluate_policy
from app.policies.schemas import MerchantPolicyConfig, PolicyEvaluationContext
from app.recovery.service import merchant_policy_from_model
from app.workflows.events import RecoveryEvent
from app.workflows.exceptions import CaseNotFoundError, StaleVersionError
from app.workflows.recovery import RecoveryAnalysisWorkflowService
from app.workflows.schemas import TransitionContext
from app.workflows.state_machine import RecoveryCaseStateMachine

TERMINAL_STATUSES = frozenset(
    {
        RecoveryCaseStatus.RECOVERED,
        RecoveryCaseStatus.FAILED,
        RecoveryCaseStatus.STOPPED,
    }
)
PROMPT16_EXECUTABLE = frozenset(
    {RecoveryActionType.WAIT, RecoveryActionType.STOP, RecoveryActionType.CREATE_PAYMENT_LINK}
)
IN_FLIGHT_STATUSES = frozenset(
    {
        RecoveryActionStatus.PENDING_APPROVAL.value,
        RecoveryActionStatus.EXECUTING.value,
        RecoveryActionStatus.UNKNOWN.value,
        RecoveryActionStatus.SCHEDULED.value,
    }
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ActionResponsePayload:
    action: RecoveryAction
    case_status: RecoveryCaseStatus
    customer_action_type: str | None = None
    customer_action_url: str | None = None


@dataclass(frozen=True)
class ApproveActionResult:
    action_id: UUID
    action_status: RecoveryActionStatus
    case_status: RecoveryCaseStatus


@dataclass(frozen=True)
class RejectActionResult:
    action_id: UUID
    action_status: RecoveryActionStatus
    case_status: RecoveryCaseStatus


UNRESOLVED_PAYMENT_LINK_STATUSES = frozenset(
    {
        RecoveryActionStatus.EXECUTING.value,
        RecoveryActionStatus.UNKNOWN.value,
    }
)


class RecoveryActionService:
    persist_provider_success_hook: Callable[[RecoveryAction, RecoveryCase, object], None] | None = (
        None
    )

    def __init__(
        self,
        session: Session,
        *,
        settings: Settings,
        state_machine: RecoveryCaseStateMachine | None = None,
        razorpay_client: RazorpayClient | None = None,
        analysis_workflow: RecoveryAnalysisWorkflowService | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._state_machine = state_machine or RecoveryCaseStateMachine()
        self._repo = RecoveryActionRepository(session)
        self._razorpay_client = razorpay_client
        self._analysis_workflow = analysis_workflow

    def create_case_action(
        self,
        *,
        case_id: UUID,
        organization_id: UUID,
        analysis_run_id: UUID,
        action_type: RecoveryActionType,
        actor_type: AuditActorType,
        actor_id: str | None,
    ) -> ActionResponsePayload:
        if action_type not in PROMPT16_EXECUTABLE:
            raise UnsupportedActionError(
                f"Action type {action_type.value} is not executable in Prompt 16."
            )
        case = self._repo.lock_case(case_id=case_id, organization_id=organization_id)
        if case is None:
            raise CaseNotFoundError(case_id=case_id, organization_id=organization_id)
        recommendation = self._load_current_recommendation(
            case=case, analysis_run_id=analysis_run_id, action_type=action_type
        )
        idempotency_key = build_action_idempotency_key(
            case_id=case.id,
            recommendation_id=recommendation.id,
            action_type=action_type.value,
        )
        existing = self._repo.get_by_idempotency_key(idempotency_key)
        if existing is not None:
            refreshed_case = self._reload_case(case.id, organization_id)
            if existing.action_type == RecoveryActionType.CREATE_PAYMENT_LINK.value:
                self._maybe_reconcile_payment_link_action(existing, refreshed_case)
                self._session.refresh(existing)
            return self._to_payload(existing, self._reload_case(case.id, organization_id))
        self._ensure_case_actionable(case)
        policy_decision = self._evaluate_current_policy(case, recommendation, auto_execute=True)
        if not policy_decision.eligible:
            raise ActionBlockedByPolicyError(
                reasons=tuple(reason.value for reason in policy_decision.reasons)
            )
        blocking = self._repo.get_blocking_payment_link_action(
            case_id=case.id, organization_id=organization_id
        )
        if blocking is not None and action_type == RecoveryActionType.CREATE_PAYMENT_LINK:
            raise ActionConflictError("Unresolved payment link action blocks new link creation.")
        try:
            if action_type == RecoveryActionType.STOP:
                return self._execute_stop(
                    case, recommendation, idempotency_key, actor_type, actor_id
                )
            if action_type == RecoveryActionType.WAIT:
                return self._execute_wait(
                    case,
                    recommendation,
                    idempotency_key,
                    self._load_policy(organization_id),
                    actor_type,
                    actor_id,
                )
            if policy_decision.requires_approval:
                return self._stage_pending_approval(
                    case, recommendation, idempotency_key, actor_type, actor_id
                )
            return self._execute_payment_link_now(
                case, recommendation, idempotency_key, actor_type, actor_id, None
            )
        except IntegrityError:
            self._session.rollback()
            existing = self._repo.get_by_idempotency_key(idempotency_key)
            if existing is None:
                raise
            return self._to_payload(existing, self._reload_case(case.id, organization_id))

    def approve_action(
        self,
        *,
        action_id: UUID,
        organization_id: UUID,
        expected_case_version: int,
        approver_id: UUID,
        actor_type: AuditActorType,
    ) -> ApproveActionResult:
        action = self._repo.get_by_id(action_id=action_id, organization_id=organization_id)
        if action is None:
            raise ActionNotFoundError(f"Recovery action {action_id} not found.")
        case = self._repo.lock_case(case_id=action.case_id, organization_id=organization_id)
        if case is None:
            raise CaseNotFoundError(case_id=action.case_id, organization_id=organization_id)
        if RecoveryCaseStatus(case.status) in TERMINAL_STATUSES:
            raise CaseNotActionableError("Case is already resolved.")
        if action.status != RecoveryActionStatus.PENDING_APPROVAL.value:
            raise ActionConflictError("Action is not pending approval.")
        if case.status != RecoveryCaseStatus.AWAITING_APPROVAL.value:
            raise ActionConflictError("Case is not awaiting approval.")
        if case.version != expected_case_version:
            raise StaleVersionError(
                case_id=case.id,
                expected_version=expected_case_version,
                actual_version=case.version,
            )
        if action.recommendation_id is not None:
            self._verify_recommendation_current(
                case=case,
                recommendation_id=action.recommendation_id,
                action_type=RecoveryActionType(action.action_type),
            )
        blocking = self._repo.get_blocking_payment_link_action(
            case_id=case.id,
            organization_id=organization_id,
        )
        if blocking is not None and blocking.id != action.id:
            raise ActionConflictError("Unresolved payment link action blocks approval.")
        now = _utcnow()
        action.approved_by = approver_id
        action.approved_at = now
        action.status = RecoveryActionStatus.EXECUTING.value
        action.execution_started_at = now
        self._session.flush()
        self._transition(
            case=case,
            event=RecoveryEvent.APPROVED_NOW,
            context=TransitionContext(
                organization_id=organization_id,
                actor_type=actor_type,
                actor_id=str(approver_id),
                action_id=action.id,
                approver_id=approver_id,
            ),
        )
        case = self._reload_case(case.id, organization_id)
        if action.action_type == RecoveryActionType.CREATE_PAYMENT_LINK.value:
            self._invoke_payment_link_provider(action, case)
            case = self._reload_case(case.id, organization_id)
        return ApproveActionResult(
            action_id=action.id,
            action_status=RecoveryActionStatus(action.status),
            case_status=RecoveryCaseStatus(case.status),
        )

    def reject_action(
        self,
        *,
        action_id: UUID,
        organization_id: UUID,
        reason: str,
        reanalyze: bool,
        actor_id: str | None,
        actor_type: AuditActorType,
    ) -> RejectActionResult:
        action = self._repo.get_by_id(action_id=action_id, organization_id=organization_id)
        if action is None:
            raise ActionNotFoundError(f"Recovery action {action_id} not found.")
        if action.status != RecoveryActionStatus.PENDING_APPROVAL.value:
            raise ActionConflictError("Action is not pending approval.")
        case = self._repo.lock_case(case_id=action.case_id, organization_id=organization_id)
        if case is None:
            raise CaseNotFoundError(case_id=action.case_id, organization_id=organization_id)
        if RecoveryCaseStatus(case.status) in TERMINAL_STATUSES:
            raise CaseNotActionableError("Case is already resolved.")
        action.status = RecoveryActionStatus.CANCELLED.value
        action.error_message = reason.strip()
        action.metadata_ = {**action.metadata_, "rejection_reason": reason.strip()}
        self._session.flush()
        event = (
            RecoveryEvent.APPROVAL_REJECTED_REANALYZE
            if reanalyze
            else RecoveryEvent.APPROVAL_REJECTED_STOP
        )
        self._transition(
            case=case,
            event=event,
            context=TransitionContext(
                organization_id=organization_id,
                actor_type=actor_type,
                actor_id=actor_id,
                reason=reason.strip(),
                rejection_recorded=True,
            ),
        )
        if reanalyze:
            rejected_type = RecoveryActionType(action.action_type)
            self._analysis_workflow_service().complete_immediate_reanalysis(
                case_id=case.id,
                organization_id=organization_id,
                excluded_action_types=frozenset({rejected_type}),
                actor_type=actor_type,
                actor_id=actor_id,
                reason=f"APPROVAL_REJECTED:{reason.strip()}",
            )
        case = self._reload_case(case.id, organization_id)
        return RejectActionResult(
            action_id=action.id,
            action_status=RecoveryActionStatus(action.status),
            case_status=RecoveryCaseStatus(case.status),
        )

    def _execute_stop(
        self,
        case: RecoveryCase,
        recommendation: RecoveryRecommendation,
        idempotency_key: str,
        actor_type: AuditActorType,
        actor_id: str | None,
    ) -> ActionResponsePayload:
        del idempotency_key, recommendation
        self._transition(
            case=case,
            event=RecoveryEvent.STOP_SELECTED,
            context=TransitionContext(
                organization_id=case.organization_id,
                actor_type=actor_type,
                actor_id=actor_id,
                reason="Operator selected STOP.",
            ),
        )
        return ActionResponsePayload(
            action=_StopActionPlaceholder(case_id=case.id),
            case_status=RecoveryCaseStatus.STOPPED,
        )

    def _execute_wait(
        self,
        case: RecoveryCase,
        recommendation: RecoveryRecommendation,
        idempotency_key: str,
        policy: MerchantPolicyConfig,
        actor_type: AuditActorType,
        actor_id: str | None,
    ) -> ActionResponsePayload:
        scheduled_for = _derive_wait_schedule(policy)
        attempt_number = self._repo.next_attempt_number(
            case_id=case.id,
            organization_id=case.organization_id,
        )
        action = self._create_action_row(
            case=case,
            recommendation=recommendation,
            action_type=RecoveryActionType.WAIT,
            status=RecoveryActionStatus.SCHEDULED,
            attempt_number=attempt_number,
            idempotency_key=idempotency_key,
            requires_approval=False,
            scheduled_for=scheduled_for,
        )
        self._repo.add(action)
        self._transition(
            case=case,
            event=RecoveryEvent.ACTION_SCHEDULED,
            context=TransitionContext(
                organization_id=case.organization_id,
                actor_type=actor_type,
                actor_id=actor_id,
                action_id=action.id,
                analysis_run_id=recommendation.analysis_run_id,
                scheduled_for=scheduled_for,
            ),
        )
        case = self._reload_case(case.id, case.organization_id)
        return self._to_payload(action, case)

    def _stage_pending_approval(
        self,
        case: RecoveryCase,
        recommendation: RecoveryRecommendation,
        idempotency_key: str,
        actor_type: AuditActorType,
        actor_id: str | None,
    ) -> ActionResponsePayload:
        attempt_number = self._repo.next_attempt_number(
            case_id=case.id,
            organization_id=case.organization_id,
        )
        action = self._create_action_row(
            case=case,
            recommendation=recommendation,
            action_type=RecoveryActionType(recommendation.action_type),
            status=RecoveryActionStatus.PENDING_APPROVAL,
            attempt_number=attempt_number,
            idempotency_key=idempotency_key,
            requires_approval=True,
        )
        if action.action_type == RecoveryActionType.CREATE_PAYMENT_LINK.value:
            action.provider_reference = build_payment_link_reference_id(action.id)
            action.request_fingerprint = build_request_fingerprint(
                amount_minor=case.amount_at_risk_minor,
                currency=case.currency,
                reference_id=action.provider_reference,
            )
        self._repo.add(action)
        self._transition(
            case=case,
            event=RecoveryEvent.APPROVAL_REQUIRED,
            context=TransitionContext(
                organization_id=case.organization_id,
                actor_type=actor_type,
                actor_id=actor_id,
                action_id=action.id,
                analysis_run_id=recommendation.analysis_run_id,
            ),
        )
        case = self._reload_case(case.id, case.organization_id)
        return self._to_payload(action, case)

    def _execute_payment_link_now(
        self,
        case: RecoveryCase,
        recommendation: RecoveryRecommendation,
        idempotency_key: str,
        actor_type: AuditActorType,
        actor_id: str | None,
        approver_id: UUID | None,
    ) -> ActionResponsePayload:
        attempt_number = self._repo.next_attempt_number(
            case_id=case.id,
            organization_id=case.organization_id,
        )
        now = _utcnow()
        action = self._create_action_row(
            case=case,
            recommendation=recommendation,
            action_type=RecoveryActionType.CREATE_PAYMENT_LINK,
            status=RecoveryActionStatus.EXECUTING,
            attempt_number=attempt_number,
            idempotency_key=idempotency_key,
            requires_approval=approver_id is not None,
            approved_by=approver_id,
            approved_at=now if approver_id else None,
            execution_started_at=now,
        )
        action.provider_reference = build_payment_link_reference_id(action.id)
        action.request_fingerprint = build_request_fingerprint(
            amount_minor=case.amount_at_risk_minor,
            currency=case.currency,
            reference_id=action.provider_reference,
        )
        self._repo.add(action)
        self._transition(
            case=case,
            event=RecoveryEvent.AUTO_EXECUTE,
            context=TransitionContext(
                organization_id=case.organization_id,
                actor_type=actor_type,
                actor_id=actor_id,
                action_id=action.id,
                approver_id=approver_id,
            ),
        )
        self._invoke_payment_link_provider(action, case)
        case = self._reload_case(case.id, case.organization_id)
        return self._to_payload(action, case)

    def _invoke_payment_link_provider(
        self,
        action: RecoveryAction,
        case: RecoveryCase,
    ) -> None:
        if action.provider_reference is None:
            action.provider_reference = build_payment_link_reference_id(action.id)
        customer_name = self._load_customer_name(case.customer_id, case.organization_id)
        client = self._resolve_razorpay_client()
        if client is None:
            self._mark_provider_unknown(action, case, error_category="PROVIDER_NOT_CONFIGURED")
            return
        try:
            result = create_payment_link(
                client,
                amount_minor=case.amount_at_risk_minor,
                currency=case.currency,
                reference_id=action.provider_reference,
                case_id=case.id,
                customer_name=customer_name,
            )
        except PaymentLinkSideEffectUnknownError:
            self._mark_provider_unknown(action, case, error_category="AMBIGUOUS_PROVIDER_RESPONSE")
            return
        except RazorpayTimeoutUnknownResult:
            self._mark_provider_unknown(action, case, error_category="PROVIDER_TIMEOUT")
            return
        except (RazorpayTransientError, RazorpayRateLimitError):
            self._mark_provider_unknown(action, case, error_category="PROVIDER_TRANSIENT")
            return
        except RazorpayAuthenticationError:
            self._mark_provider_failed(action, case, error_category="PROVIDER_AUTH", reanalyze=True)
            return
        except RazorpayValidationError as exc:
            message = str(exc).lower()
            if "reference" in message and "exist" in message:
                self._mark_provider_unknown(action, case, error_category="DUPLICATE_REFERENCE")
                return
            self._mark_provider_failed(
                action,
                case,
                error_category="PROVIDER_VALIDATION",
                reanalyze=self._safe_to_reanalyze(case),
            )
            return
        except RazorpayApiError:
            self._mark_provider_unknown(action, case, error_category="PROVIDER_ERROR")
            return

        self._persist_provider_success(action, case, result)

    def _persist_provider_success(
        self,
        action: RecoveryAction,
        case: RecoveryCase,
        result: object,
    ) -> None:
        if RecoveryActionService.persist_provider_success_hook is not None:
            RecoveryActionService.persist_provider_success_hook(action, case, result)
        from app.integrations.razorpay.schemas import PaymentLinkCreateResult

        if not isinstance(result, PaymentLinkCreateResult):
            raise TypeError("Expected PaymentLinkCreateResult for provider success persistence.")
        action.status = RecoveryActionStatus.SUCCEEDED.value
        action.provider_status = result.status
        action.executed_at = _utcnow()
        action.metadata_ = {
            **action.metadata_,
            "provider_payment_link_id": result.id,
            "short_url": result.short_url,
        }
        self._session.flush()
        self._session.commit()
        refreshed = self._reload_case(case.id, case.organization_id)
        if RecoveryCaseStatus(refreshed.status) == RecoveryCaseStatus.EXECUTING:
            self._transition(
                case=refreshed,
                event=RecoveryEvent.ACTION_ACCEPTED_OR_UNKNOWN,
                context=TransitionContext(
                    organization_id=case.organization_id,
                    actor_type=AuditActorType.SYSTEM,
                    action_id=action.id,
                ),
            )

    def _maybe_reconcile_payment_link_action(
        self,
        action: RecoveryAction,
        case: RecoveryCase,
    ) -> None:
        if action.action_type != RecoveryActionType.CREATE_PAYMENT_LINK.value:
            return
        if action.provider_reference is None:
            return
        unresolved = action.status in UNRESOLVED_PAYMENT_LINK_STATUSES
        missing_link_id = not action.metadata_.get("provider_payment_link_id")
        succeeded_missing_id = (
            action.status == RecoveryActionStatus.SUCCEEDED.value and missing_link_id
        )
        if not unresolved and not succeeded_missing_id:
            return
        client = self._resolve_razorpay_client()
        if client is None:
            return
        try:
            outcome = fetch_payment_links_by_reference(
                client,
                reference_id=action.provider_reference,
                amount_minor=case.amount_at_risk_minor,
                currency=case.currency,
            )
        except (RazorpayTimeoutUnknownResult, RazorpayTransientError, RazorpayRateLimitError):
            return
        except RazorpayValidationError:
            return
        except RazorpayApiError:
            return

        if outcome.status == "not_found":
            return
        if outcome.status == "ambiguous" or outcome.link is None:
            action.error_category = "RECONCILIATION_AMBIGUOUS"
            action.metadata_ = {**action.metadata_, "reconciliation_status": "ambiguous"}
            self._session.flush()
            self._session.commit()
            return

        self._apply_reconciled_payment_link(action, case, outcome.link)

    def _apply_reconciled_payment_link(
        self,
        action: RecoveryAction,
        case: RecoveryCase,
        result: object,
    ) -> None:
        from app.integrations.razorpay.schemas import PaymentLinkCreateResult

        if not isinstance(result, PaymentLinkCreateResult):
            raise TypeError("Expected PaymentLinkCreateResult for reconciliation.")
        action.status = RecoveryActionStatus.SUCCEEDED.value
        action.provider_status = result.status
        action.executed_at = action.executed_at or _utcnow()
        action.error_category = None
        action.metadata_ = {
            **action.metadata_,
            "provider_payment_link_id": result.id,
            "short_url": result.short_url,
            "reconciliation_status": "matched",
        }
        self._session.flush()
        self._session.commit()
        refreshed = self._reload_case(case.id, case.organization_id)
        if RecoveryCaseStatus(refreshed.status) == RecoveryCaseStatus.EXECUTING:
            self._transition(
                case=refreshed,
                event=RecoveryEvent.ACTION_ACCEPTED_OR_UNKNOWN,
                context=TransitionContext(
                    organization_id=case.organization_id,
                    actor_type=AuditActorType.SYSTEM,
                    action_id=action.id,
                ),
            )

    def _analysis_workflow_service(self) -> RecoveryAnalysisWorkflowService:
        if self._analysis_workflow is not None:
            return self._analysis_workflow
        return RecoveryAnalysisWorkflowService(self._session, settings=self._settings)

    def _mark_provider_unknown(
        self,
        action: RecoveryAction,
        case: RecoveryCase,
        *,
        error_category: str,
    ) -> None:
        action.status = RecoveryActionStatus.UNKNOWN.value
        action.error_category = error_category
        action.executed_at = _utcnow()
        self._session.flush()
        self._session.commit()
        refreshed = self._reload_case(case.id, case.organization_id)
        self._transition(
            case=refreshed,
            event=RecoveryEvent.ACTION_ACCEPTED_OR_UNKNOWN,
            context=TransitionContext(
                organization_id=case.organization_id,
                actor_type=AuditActorType.SYSTEM,
                action_id=action.id,
            ),
        )

    def _mark_provider_failed(
        self,
        action: RecoveryAction,
        case: RecoveryCase,
        *,
        error_category: str,
        reanalyze: bool,
    ) -> None:
        action.status = RecoveryActionStatus.FAILED.value
        action.error_category = error_category
        action.executed_at = _utcnow()
        self._session.flush()
        self._session.commit()
        refreshed = self._reload_case(case.id, case.organization_id)
        event = (
            RecoveryEvent.ACTION_FAILED_REANALYZE
            if reanalyze
            else RecoveryEvent.TERMINAL_ACTION_FAILURE
        )
        self._transition(
            case=refreshed,
            event=event,
            context=TransitionContext(
                organization_id=case.organization_id,
                actor_type=AuditActorType.SYSTEM,
                action_id=action.id,
                reason=f"Payment link creation failed ({error_category}).",
            ),
        )

    def _safe_to_reanalyze(self, case: RecoveryCase) -> bool:
        policy = self._load_policy(case.organization_id)
        attempts = self._count_recovery_attempts(case)
        return attempts < policy.max_recovery_attempts

    def _resolve_razorpay_client(self) -> RazorpayClient | None:
        if self._razorpay_client is not None:
            return self._razorpay_client
        handle = acquire_razorpay_read_client(self._settings, injected=None)
        return handle.client if handle is not None else None

    def _load_customer_name(self, customer_id: UUID, organization_id: UUID) -> str | None:
        customer = self._session.execute(
            select(Customer).where(
                Customer.id == customer_id,
                Customer.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        return customer.display_name if customer is not None else None

    def _create_action_row(
        self,
        *,
        case: RecoveryCase,
        recommendation: RecoveryRecommendation,
        action_type: RecoveryActionType,
        status: RecoveryActionStatus,
        attempt_number: int,
        idempotency_key: str,
        requires_approval: bool,
        scheduled_for: datetime | None = None,
        approved_by: UUID | None = None,
        approved_at: datetime | None = None,
        execution_started_at: datetime | None = None,
    ) -> RecoveryAction:
        return RecoveryAction(
            id=uuid.uuid4(),
            organization_id=case.organization_id,
            case_id=case.id,
            recommendation_id=recommendation.id,
            action_type=action_type.value,
            status=status.value,
            attempt_number=attempt_number,
            requires_approval=requires_approval,
            approved_by=approved_by,
            approved_at=approved_at,
            idempotency_key=idempotency_key,
            scheduled_for=scheduled_for,
            execution_started_at=execution_started_at,
        )

    def _transition(
        self,
        *,
        case: RecoveryCase,
        event: RecoveryEvent,
        context: TransitionContext,
    ) -> None:
        self._state_machine.transition_case(
            self._session,
            case_id=case.id,
            organization_id=case.organization_id,
            expected_version=case.version,
            event=event,
            context=context,
        )

    def _ensure_case_actionable(self, case: RecoveryCase) -> None:
        status = RecoveryCaseStatus(case.status)
        if status in TERMINAL_STATUSES:
            raise CaseNotActionableError("Case is already resolved.")
        if status != RecoveryCaseStatus.RECOMMENDED:
            raise CaseNotActionableError(f"Case status {status.value} cannot initiate actions.")

    def _load_current_recommendation(
        self,
        *,
        case: RecoveryCase,
        analysis_run_id: UUID,
        action_type: RecoveryActionType,
    ) -> RecoveryRecommendation:
        if case.current_analysis_run_id != analysis_run_id:
            raise StaleRecommendationError("Analysis run is no longer current for this case.")
        recommendation = self._session.execute(
            select(RecoveryRecommendation).where(
                RecoveryRecommendation.case_id == case.id,
                RecoveryRecommendation.organization_id == case.organization_id,
                RecoveryRecommendation.analysis_run_id == analysis_run_id,
                RecoveryRecommendation.action_type == action_type.value,
                RecoveryRecommendation.rank == 1,
            )
        ).scalar_one_or_none()
        if recommendation is None:
            raise StaleRecommendationError("Selected recommendation not found for analysis run.")
        if not recommendation.policy_eligible:
            raise ActionBlockedByPolicyError(reasons=tuple(recommendation.policy_reasons or ()))
        return recommendation

    def _verify_recommendation_current(
        self,
        *,
        case: RecoveryCase,
        recommendation_id: UUID,
        action_type: RecoveryActionType,
    ) -> None:
        recommendation = self._session.execute(
            select(RecoveryRecommendation).where(
                RecoveryRecommendation.id == recommendation_id,
                RecoveryRecommendation.case_id == case.id,
                RecoveryRecommendation.organization_id == case.organization_id,
            )
        ).scalar_one_or_none()
        if recommendation is None:
            raise StaleRecommendationError("Recommendation no longer belongs to case.")
        if case.current_analysis_run_id != recommendation.analysis_run_id:
            raise StaleRecommendationError("Recommendation analysis run is stale.")
        if recommendation.rank != 1 or recommendation.action_type != action_type.value:
            raise StaleRecommendationError("Recommendation is no longer selected.")

    def _evaluate_current_policy(
        self,
        case: RecoveryCase,
        recommendation: RecoveryRecommendation,
        *,
        auto_execute: bool,
    ):
        policy = self._load_policy(case.organization_id)
        context = self._build_policy_context(
            case=case,
            recommendation=recommendation,
            policy=policy,
            auto_execute=auto_execute,
        )
        return evaluate_policy(context, policy)

    def _build_policy_context(
        self,
        *,
        case: RecoveryCase,
        recommendation: RecoveryRecommendation,
        policy: MerchantPolicyConfig,
        auto_execute: bool,
    ) -> PolicyEvaluationContext:
        attempts = self._count_recovery_attempts(case)
        in_flight: set[RecoveryActionType] = set()
        blocking = self._repo.get_blocking_payment_link_action(
            case_id=case.id,
            organization_id=case.organization_id,
        )
        if blocking is not None:
            in_flight.add(RecoveryActionType.CREATE_PAYMENT_LINK)
        return PolicyEvaluationContext(
            action_type=RecoveryActionType(recommendation.action_type),
            amount_at_risk_minor=case.amount_at_risk_minor,
            recovery_attempts_so_far=attempts,
            contacts_last_24h=0,
            confidence=recommendation.confidence,
            expected_value_minor=recommendation.expected_value_minor,
            payment_link_data_sufficient=case.amount_at_risk_minor > 0 and bool(case.currency),
            case_terminal=False,
            provider_success_known=False,
            equivalent_actions_in_flight=frozenset(in_flight),
            auto_execution_requested=auto_execute,
            cooldown_elapsed_minutes=999,
        )

    def _count_recovery_attempts(self, case: RecoveryCase) -> int:
        return self._repo.count_actions(
            case_id=case.id,
            organization_id=case.organization_id,
        )

    def _load_policy(self, organization_id: UUID) -> MerchantPolicyConfig:
        policy_row = self._session.execute(
            select(MerchantPolicy).where(MerchantPolicy.organization_id == organization_id)
        ).scalar_one_or_none()
        if policy_row is None:
            raise ActionBlockedByPolicyError(reasons=("POLICY_NOT_FOUND",))
        return merchant_policy_from_model(policy_row)

    def _reload_case(self, case_id: UUID, organization_id: UUID) -> RecoveryCase:
        case = self._session.execute(
            select(RecoveryCase).where(
                RecoveryCase.id == case_id,
                RecoveryCase.organization_id == organization_id,
            )
        ).scalar_one()
        return case

    def _to_payload(
        self,
        action: RecoveryAction,
        case: RecoveryCase,
    ) -> ActionResponsePayload:
        customer_action_type = None
        customer_action_url = None
        if action.action_type == RecoveryActionType.CREATE_PAYMENT_LINK.value:
            short_url = action.metadata_.get("short_url")
            if short_url:
                customer_action_type = "PAYMENT_LINK"
                customer_action_url = str(short_url)
        return ActionResponsePayload(
            action=action,
            case_status=RecoveryCaseStatus(case.status),
            customer_action_type=customer_action_type,
            customer_action_url=customer_action_url,
        )


@dataclass(frozen=True)
class _StopActionPlaceholder:
    """Synthetic action view for STOP responses without a persisted action row."""

    case_id: UUID
    id: UUID = uuid.UUID(int=0)
    action_type: str = RecoveryActionType.STOP.value
    status: str = RecoveryActionStatus.SUCCEEDED.value
    requires_approval: bool = False
    provider_reference: str | None = None
    scheduled_for: datetime | None = None


def _derive_wait_schedule(policy: MerchantPolicyConfig) -> datetime:
    return _utcnow() + timedelta(minutes=max(policy.cooldown_minutes, 1))
