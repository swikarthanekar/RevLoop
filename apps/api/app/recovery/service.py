"""Recovery analysis orchestration service (Prompt 13)."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.domain.enums import (
    AnalysisReason,
    CaseType,
    RecoveryActionType,
    RecoveryCaseStatus,
)
from app.integrations.razorpay.client import RazorpayClient
from app.integrations.razorpay.provider import (
    RazorpayClientFactory,
    acquire_razorpay_read_client,
)
from app.ml.fallback import FALLBACK_MODEL_VERSION, get_fallback_probability
from app.ml.schemas import ActionProbability, ModelInferenceResult
from app.ml.service import (
    ModelArtifactError,
    ModelInferenceError,
    RecoveryPropensityModelService,
)
from app.models.customer import Customer
from app.models.merchant_policy import MerchantPolicy
from app.models.recovery_action import RecoveryAction
from app.models.recovery_case import RecoveryCase
from app.models.subscription import Subscription
from app.models.transaction import Transaction
from app.policies.engine import evaluate_policy
from app.policies.schemas import MerchantPolicyConfig, PolicyEvaluationContext
from app.recovery.candidates import generate_candidates
from app.recovery.confidence import calculate_confidence
from app.recovery.context import resolve_downtime_context
from app.recovery.erv import calculate_erv
from app.recovery.failure_normalizer import (
    normalize_payment_failure,
    normalize_subscription_failure,
)
from app.recovery.features import build_recovery_features_v1
from app.recovery.ranking import OPERATIONAL_BURDEN, rank_candidates, select_recommendation
from app.recovery.schemas import (
    CandidateGenerationContext,
    CaseSnapshot,
    CustomerSnapshot,
    DowntimeContext,
    FeatureBuildInput,
    PaymentFailureEvidence,
    RankedRecommendationCandidate,
    RecommendationCandidate,
    RecoveryFeaturesV1,
    SubscriptionFailureEvidence,
    SubscriptionSnapshot,
    TransactionSnapshot,
)
from app.repositories.recovery_analysis import (
    CaseAnalysisSummaryUpdate,
    RecommendationPersistenceRow,
    RecoveryAnalysisRepository,
)

logger = logging.getLogger(__name__)

SUBSCRIPTION_PENDING_STATUS = "pending"
SUBSCRIPTION_HALTED_STATUS = "halted"


class InsufficientCaseDataError(Exception):
    """Raised when required case context is missing for analysis."""


class ModelUnavailableError(Exception):
    """Raised when model inference fails and fallback is disabled."""


class InvalidCaseStateForAnalysisError(Exception):
    """Raised when analysis reason is not valid for the current case status."""


@dataclass(frozen=True)
class AnalysisComputationResult:
    analysis_run_id: UUID
    ranked_candidates: list[RankedRecommendationCandidate]
    selected: RankedRecommendationCandidate | None
    inference: ModelInferenceResult
    priority_score: Decimal
    case_update: CaseAnalysisSummaryUpdate
    recommendation_rows: list[RecommendationPersistenceRow]


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _to_decimal(value: float | Decimal) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def build_model_metadata_factors(inference: ModelInferenceResult) -> list[dict[str, str]]:
    factors = [
        {
            "code": "MODEL_METADATA",
            "model_family": inference.model_family,
            "model_version": inference.model_version,
            "feature_schema_version": inference.feature_schema_version,
            "artifact_sha256": inference.artifact_sha256,
            "inference_source": inference.source,
        }
    ]
    if inference.fallback_reason:
        factors.append(
            {
                "code": "INFERENCE_FALLBACK",
                "impact": "HIGH",
                "source": inference.fallback_reason,
            }
        )
    return factors


def build_explainable_factors(
    *,
    features: RecoveryFeaturesV1,
    action: RecoveryActionType,
) -> list[dict[str, str]]:
    factors: list[dict[str, str]] = []
    if features.rail_degraded:
        factors.append(
            {
                "code": "ACTIVE_RAIL_DOWNTIME",
                "impact": "HIGH",
                "source": "DOWNTIME",
            }
        )
    if features.same_method_recent_success:
        factors.append(
            {
                "code": "RECENT_METHOD_SUCCESS",
                "impact": "MEDIUM",
                "source": "TRANSACTION_HISTORY",
            }
        )
    if features.contacts_last_24h == 0:
        factors.append(
            {
                "code": "NO_RECENT_CONTACTS",
                "impact": "LOW",
                "source": "RECOVERY_HISTORY",
            }
        )
    if action == RecoveryActionType.STOP:
        factors.append(
            {
                "code": "STOP_SAFE_FLOOR",
                "impact": "HIGH",
                "source": "DECISION_ENGINE",
            }
        )
    return factors


def calculate_priority_score(
    *,
    selected_erv: int,
    merchant_erv_scale_minor: int,
    hours_since_failure: float,
    lifetime_value_log1p: float,
    confidence: Decimal,
) -> Decimal:
    scale = max(merchant_erv_scale_minor, 1)
    normalized_erv = min(max(selected_erv / scale, 0.0), 1.0)
    urgency = min(max(hours_since_failure / 168.0, 0.0), 1.0)
    customer_value = min(max(lifetime_value_log1p / 15.0, 0.0), 1.0)
    confidence_value = float(confidence)
    score = (
        0.50 * normalized_erv
        + 0.20 * urgency
        + 0.15 * customer_value
        + 0.15 * confidence_value
    )
    return _to_decimal(min(max(score, 0.0), 1.0))


def merchant_policy_from_model(policy: MerchantPolicy) -> MerchantPolicyConfig:
    allowed = frozenset(RecoveryActionType(value) for value in policy.allowed_action_types)
    return MerchantPolicyConfig(
        auto_action_limit_minor=policy.auto_action_limit_minor,
        max_recovery_attempts=policy.max_recovery_attempts,
        max_contacts_per_24h=policy.max_contacts_per_24h,
        minimum_auto_confidence=policy.minimum_auto_confidence,
        cooldown_minutes=policy.cooldown_minutes,
        automation_enabled=policy.automation_enabled,
        allowed_action_types=allowed,
    )


class RecoveryAnalysisService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        propensity_model: RecoveryPropensityModelService | None = None,
        allow_model_fallback: bool = True,
        razorpay_client: RazorpayClient | None = None,
        razorpay_client_factory: RazorpayClientFactory | None = None,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._propensity_model = propensity_model or RecoveryPropensityModelService()
        self._allow_model_fallback = allow_model_fallback
        self._analysis_repo = RecoveryAnalysisRepository(session)
        self._razorpay_client = razorpay_client
        self._razorpay_client_factory = razorpay_client_factory

    def _resolve_downtime_context(self, transaction: Transaction | None) -> DowntimeContext:
        handle = acquire_razorpay_read_client(
            self._settings,
            injected=self._razorpay_client,
            factory=self._razorpay_client_factory,
        )
        if handle is None:
            return resolve_downtime_context(
                None,
                transaction,
                lookup_configured=False,
            )
        try:
            return resolve_downtime_context(
                handle.client,
                transaction,
                lookup_configured=True,
            )
        finally:
            if handle.owned:
                handle.client.close()

    def compute_analysis(
        self,
        *,
        case: RecoveryCase,
        analysis_run_id: UUID | None = None,
        current_time: datetime | None = None,
    ) -> AnalysisComputationResult:
        run_id = analysis_run_id or uuid.uuid4()
        now = current_time or _utcnow()

        customer = self._load_customer(case)
        transaction, subscription = self._load_revenue_source(case)
        policy = self._load_merchant_policy(case.organization_id)
        prior_transactions = self._load_prior_transactions(case, customer.id)
        recovery_attempts, contacts_last_24h = self._load_recovery_counters(case, now)
        prior_total, prior_recovered = self._load_prior_recovery_counts(case, customer.id)

        downtime = self._resolve_downtime_context(transaction)
        normalization = self._normalize_failure(
            case,
            transaction,
            subscription,
            downtime=downtime,
        )
        candidate_context = self._build_candidate_context(
            case,
            normalization.failure_category,
            subscription,
            downtime=downtime,
        )
        candidate_actions = generate_candidates(candidate_context)

        base_features = self._build_case_features(
            case=case,
            customer=customer,
            transaction=transaction,
            subscription=subscription,
            normalization=normalization,
            prior_transactions=prior_transactions,
            recovery_attempts=recovery_attempts,
            contacts_last_24h=contacts_last_24h,
            prior_total=prior_total,
            prior_recovered=prior_recovered,
            current_time=now,
            downtime=downtime,
        )
        inference = self._score_actions(
            features=base_features,
            actions=candidate_actions,
            candidate_context=candidate_context,
        )
        probability_by_action = {
            entry.action_type: _to_decimal(entry.probability) for entry in inference.probabilities
        }

        recommendation_candidates: list[RecommendationCandidate] = []
        for action in candidate_actions:
            action_features = base_features.model_copy(update={"action_type": action.value})
            probability = probability_by_action.get(action)
            if probability is None:
                raise ModelInferenceError(f"Missing probability for action {action.value}.")
            erv = calculate_erv(
                action=action,
                amount_at_risk_minor=case.amount_at_risk_minor,
                success_probability=probability,
                contacts_last_24h=contacts_last_24h,
            )
            confidence = calculate_confidence(
                feature_completeness=action_features.feature_completeness,
                success_probability=probability,
                evidence_strength=_to_decimal(action_features.evidence_strength),
            )
            policy_context = PolicyEvaluationContext(
                action_type=action,
                amount_at_risk_minor=case.amount_at_risk_minor,
                recovery_attempts_so_far=recovery_attempts,
                contacts_last_24h=contacts_last_24h,
                confidence=confidence,
                expected_value_minor=erv.expected_value_minor,
                payment_link_data_sufficient=candidate_context.payment_link_data_sufficient,
                case_terminal=False,
                provider_success_known=False,
                verified_rail_downtime=normalization.failure_category.value
                == "PAYMENT_RAIL_DOWNTIME",
                equivalent_actions_in_flight=frozenset(),
                auto_execution_requested=False,
                cooldown_elapsed_minutes=999,
                provider_retries_active=candidate_context.provider_retries_active,
            )
            decision = evaluate_policy(policy_context, policy)
            recommendation_candidates.append(
                RecommendationCandidate(
                    action_type=action,
                    success_probability=probability,
                    expected_recovered_minor=erv.expected_recovered_minor,
                    expected_value_minor=erv.expected_value_minor,
                    confidence=confidence,
                    eligible=decision.eligible,
                    requires_approval=decision.requires_approval,
                    policy_reasons=tuple(reason.value for reason in decision.reasons),
                    operational_burden=OPERATIONAL_BURDEN[action],
                )
            )

        ranked = rank_candidates(recommendation_candidates)
        selected = select_recommendation(ranked)

        selected_erv = selected.expected_value_minor if selected is not None else 0
        selected_probability = (
            selected.success_probability if selected is not None else Decimal("0")
        )
        selected_confidence = selected.confidence if selected is not None else Decimal("0")
        priority_score = calculate_priority_score(
            selected_erv=selected_erv,
            merchant_erv_scale_minor=policy.auto_action_limit_minor,
            hours_since_failure=base_features.hours_since_failure,
            lifetime_value_log1p=base_features.lifetime_value_log1p,
            confidence=selected_confidence,
        )

        recommendation_rows = [
            RecommendationPersistenceRow(
                action_type=candidate.action_type.value,
                rank=candidate.rank,
                success_probability=candidate.success_probability,
                expected_recovered_minor=candidate.expected_recovered_minor,
                expected_value_minor=candidate.expected_value_minor,
                confidence=candidate.confidence,
                policy_eligible=candidate.eligible,
                requires_approval=candidate.requires_approval,
                policy_reasons=list(candidate.policy_reasons),
                factors=[
                    *build_model_metadata_factors(inference),
                    *build_explainable_factors(
                        features=base_features.model_copy(
                            update={"action_type": candidate.action_type.value}
                        ),
                        action=candidate.action_type,
                    ),
                ],
                model_version=inference.model_version,
                feature_schema_version=inference.feature_schema_version,
            )
            for candidate in ranked
        ]

        case_update = CaseAnalysisSummaryUpdate(
            current_analysis_run_id=run_id,
            priority_score=priority_score,
            recovery_probability=selected_probability,
            expected_recoverable_minor=selected.expected_recovered_minor
            if selected is not None
            else 0,
        )

        return AnalysisComputationResult(
            analysis_run_id=run_id,
            ranked_candidates=ranked,
            selected=selected,
            inference=inference,
            priority_score=priority_score,
            case_update=case_update,
            recommendation_rows=recommendation_rows,
        )

    def persist_analysis(
        self,
        *,
        case: RecoveryCase,
        result: AnalysisComputationResult,
        persisted_at: datetime | None = None,
    ) -> None:
        timestamp = persisted_at or _utcnow()
        self._analysis_repo.persist_analysis_run(
            organization_id=case.organization_id,
            case_id=case.id,
            analysis_run_id=result.analysis_run_id,
            recommendations=result.recommendation_rows,
            case_update=result.case_update,
            updated_at=timestamp,
        )
        self._session.commit()

    def _score_actions(
        self,
        *,
        features: RecoveryFeaturesV1,
        actions: list[RecoveryActionType],
        candidate_context: CandidateGenerationContext,
    ) -> ModelInferenceResult:
        try:
            return self._propensity_model.score_actions(features=features, actions=actions)
        except (ModelArtifactError, ModelInferenceError) as exc:
            logger.warning("Model inference failed: %s", exc)
            if not self._allow_model_fallback:
                raise ModelUnavailableError(str(exc)) from exc
            probabilities = []
            for action in actions:
                if action == RecoveryActionType.STOP:
                    probability = 0.0
                else:
                    probability = float(get_fallback_probability(candidate_context, action))
                probabilities.append(
                    ActionProbability(action_type=action, probability=probability)
                )
            return ModelInferenceResult(
                model_version=FALLBACK_MODEL_VERSION,
                model_family="heuristic_fallback",
                feature_schema_version=features.feature_schema_version,
                artifact_sha256="",
                source="fallback",
                fallback_reason=str(exc),
                probabilities=tuple(probabilities),
            )

    def _load_customer(self, case: RecoveryCase) -> Customer:
        customer = self._session.execute(
            select(Customer).where(
                Customer.id == case.customer_id,
                Customer.organization_id == case.organization_id,
            )
        ).scalar_one_or_none()
        if customer is None:
            raise InsufficientCaseDataError("Customer not found for recovery case.")
        return customer

    def _load_revenue_source(
        self,
        case: RecoveryCase,
    ) -> tuple[Transaction | None, Subscription | None]:
        transaction = None
        subscription = None
        if case.transaction_id is not None:
            transaction = self._session.execute(
                select(Transaction).where(
                    Transaction.id == case.transaction_id,
                    Transaction.organization_id == case.organization_id,
                )
            ).scalar_one_or_none()
            if transaction is None:
                raise InsufficientCaseDataError("Transaction not found for recovery case.")
        if case.subscription_id is not None:
            subscription = self._session.execute(
                select(Subscription).where(
                    Subscription.id == case.subscription_id,
                    Subscription.organization_id == case.organization_id,
                )
            ).scalar_one_or_none()
            if subscription is None:
                raise InsufficientCaseDataError("Subscription not found for recovery case.")
        if transaction is None and subscription is None:
            raise InsufficientCaseDataError("Recovery case has no revenue source.")
        return transaction, subscription

    def _load_merchant_policy(self, organization_id: UUID) -> MerchantPolicyConfig:
        policy = self._session.execute(
            select(MerchantPolicy).where(MerchantPolicy.organization_id == organization_id)
        ).scalar_one_or_none()
        if policy is None:
            raise InsufficientCaseDataError("Merchant policy not configured.")
        return merchant_policy_from_model(policy)

    def _load_prior_transactions(
        self,
        case: RecoveryCase,
        customer_id: UUID,
    ) -> tuple[TransactionSnapshot, ...]:
        rows = self._session.execute(
            select(Transaction).where(
                Transaction.organization_id == case.organization_id,
                Transaction.customer_id == customer_id,
            )
        ).scalars()
        snapshots = [
            TransactionSnapshot(
                id=row.id,
                organization_id=row.organization_id,
                customer_id=row.customer_id,
                amount_minor=row.amount_minor,
                currency=row.currency,
                status=row.status,
                payment_method=row.payment_method,
                error_code=row.error_code,
                error_reason=row.error_reason,
                error_source=row.error_source,
                error_step=row.error_step,
                provider_created_at=row.provider_created_at,
            )
            for row in rows
        ]
        return tuple(snapshots)

    def _load_recovery_counters(
        self,
        case: RecoveryCase,
        now: datetime,
    ) -> tuple[int, int]:
        actions = self._session.execute(
            select(RecoveryAction).where(
                RecoveryAction.case_id == case.id,
                RecoveryAction.organization_id == case.organization_id,
            )
        ).scalars()
        action_list = list(actions)
        recovery_attempts = len(action_list)
        contacts_last_24h = 0
        return recovery_attempts, contacts_last_24h

    def _load_prior_recovery_counts(
        self,
        case: RecoveryCase,
        customer_id: UUID,
    ) -> tuple[int | None, int | None]:
        total = self._session.execute(
            select(func.count())
            .select_from(RecoveryCase)
            .where(
                RecoveryCase.organization_id == case.organization_id,
                RecoveryCase.customer_id == customer_id,
                RecoveryCase.id != case.id,
            )
        ).scalar_one()
        recovered = self._session.execute(
            select(func.count())
            .select_from(RecoveryCase)
            .where(
                RecoveryCase.organization_id == case.organization_id,
                RecoveryCase.customer_id == customer_id,
                RecoveryCase.id != case.id,
                RecoveryCase.status == RecoveryCaseStatus.RECOVERED.value,
            )
        ).scalar_one()
        if total == 0:
            return None, None
        return int(total), int(recovered)

    def _normalize_failure(
        self,
        case: RecoveryCase,
        transaction: Transaction | None,
        subscription: Subscription | None,
        *,
        downtime: DowntimeContext | None = None,
    ):
        if transaction is not None:
            evidence = PaymentFailureEvidence(
                error_code=transaction.error_code,
                error_reason=transaction.error_reason,
                error_source=transaction.error_source,
                error_step=transaction.error_step,
                payment_method=transaction.payment_method,
            )
            downtime_ctx = downtime or DowntimeContext()
            return normalize_payment_failure(evidence, downtime=downtime_ctx)
        assert subscription is not None
        metadata = subscription.metadata_ or {}
        evidence = SubscriptionFailureEvidence(
            provider_status=subscription.status,
            retry_count=subscription.retry_count,
            metadata_failure_reason=metadata.get("failure_reason"),
            metadata_failure_category=metadata.get("failure_category"),
        )
        return normalize_subscription_failure(evidence)

    def _build_candidate_context(
        self,
        case: RecoveryCase,
        failure_category,
        subscription: Subscription | None,
        *,
        downtime: DowntimeContext | None = None,
    ) -> CandidateGenerationContext:
        from app.domain.enums import FailureCategory

        category = FailureCategory(failure_category)
        active_downtime = (
            downtime is not None
            and downtime.lookup_status == "KNOWN"
            and downtime.rail_degraded
        )
        if case.case_type == CaseType.PAYMENT_FAILURE.value:
            return CandidateGenerationContext(
                failure_category=category,
                case_type=CaseType.PAYMENT_FAILURE,
                active_payment_rail_downtime=active_downtime
                or category == FailureCategory.PAYMENT_RAIL_DOWNTIME,
                payment_link_data_sufficient=True,
            )
        assert subscription is not None
        return CandidateGenerationContext(
            failure_category=category,
            case_type=CaseType.SUBSCRIPTION_FAILURE,
            subscription_status=subscription.status,
            provider_retries_active=subscription.status == SUBSCRIPTION_PENDING_STATUS,
            active_payment_rail_downtime=active_downtime
            or category == FailureCategory.PAYMENT_RAIL_DOWNTIME,
            payment_link_data_sufficient=True,
        )

    def _build_case_features(
        self,
        *,
        case: RecoveryCase,
        customer: Customer,
        transaction: Transaction | None,
        subscription: Subscription | None,
        normalization,
        prior_transactions: tuple[TransactionSnapshot, ...],
        recovery_attempts: int,
        contacts_last_24h: int,
        prior_total: int | None,
        prior_recovered: int | None,
        current_time: datetime,
        downtime: DowntimeContext | None = None,
    ) -> RecoveryFeaturesV1:
        feature_input = FeatureBuildInput(
            case=CaseSnapshot(
                id=case.id,
                organization_id=case.organization_id,
                customer_id=case.customer_id,
                case_type=CaseType(case.case_type),
                amount_at_risk_minor=case.amount_at_risk_minor,
                currency=case.currency,
                opened_at=case.opened_at,
                failure_category=case.failure_category,
            ),
            customer=CustomerSnapshot(
                id=customer.id,
                organization_id=customer.organization_id,
                segment=customer.segment,
                lifetime_value_minor=customer.lifetime_value_minor,
                created_at=customer.created_at,
            ),
            normalization=normalization,
            current_time=current_time,
            transaction=(
                TransactionSnapshot(
                    id=transaction.id,
                    organization_id=transaction.organization_id,
                    customer_id=transaction.customer_id,
                    amount_minor=transaction.amount_minor,
                    currency=transaction.currency,
                    status=transaction.status,
                    payment_method=transaction.payment_method,
                    error_code=transaction.error_code,
                    error_reason=transaction.error_reason,
                    error_source=transaction.error_source,
                    error_step=transaction.error_step,
                    provider_created_at=transaction.provider_created_at,
                )
                if transaction is not None
                else None
            ),
            subscription=(
                SubscriptionSnapshot(
                    id=subscription.id,
                    organization_id=subscription.organization_id,
                    customer_id=subscription.customer_id,
                    amount_minor=subscription.amount_minor,
                    currency=subscription.currency,
                    status=subscription.status,
                    retry_count=subscription.retry_count,
                    metadata_=subscription.metadata_ or {},
                )
                if subscription is not None
                else None
            ),
            prior_transactions=prior_transactions,
            recovery_attempts_so_far=recovery_attempts,
            contacts_last_24h=contacts_last_24h,
            prior_recovery_cases_total=prior_total,
            prior_recovery_cases_recovered=prior_recovered,
            downtime=downtime,
        )
        return build_recovery_features_v1(feature_input)


def map_analysis_reason_to_event(
    *,
    status: RecoveryCaseStatus,
    reason: AnalysisReason,
):
    from app.workflows.events import RecoveryEvent

    mapping = {
        (RecoveryCaseStatus.DETECTED, AnalysisReason.MANUAL_ANALYSIS): (
            RecoveryEvent.ANALYSIS_REQUESTED
        ),
        (
            RecoveryCaseStatus.SCHEDULED,
            AnalysisReason.SCHEDULED_REEVALUATION,
        ): RecoveryEvent.REEVALUATION_DUE,
        (
            RecoveryCaseStatus.WAITING_FOR_OUTCOME,
            AnalysisReason.NEW_PROVIDER_EVIDENCE,
        ): RecoveryEvent.NEGATIVE_OUTCOME_OR_TIMEOUT,
    }
    return mapping.get((status, reason))
